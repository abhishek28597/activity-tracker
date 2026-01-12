import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import argparse
import os

# Configuration
class Config:
    # Model
    vocab_size = None  # Set from data
    n_embd = 128
    n_head = 4
    n_layer = 4
    block_size = 128
    dropout = 0.1
    
    # Training
    batch_size = 64
    learning_rate = 3e-4
    max_iters = 5000
    eval_interval = 500
    
    # System
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

# Tokenizer
class CharTokenizer:
    def __init__(self, text):
        chars = sorted(list(set(text)))
        self.vocab_size = len(chars)
        self.stoi = {ch: i for i, ch in enumerate(chars)}
        self.itos = {i: ch for i, ch in enumerate(chars)}
    
    def encode(self, s):
        return [self.stoi[c] for c in s]
    
    def decode(self, l):
        return ''.join([self.itos[i] for i in l])

# Dataset
class TextDataset(Dataset):
    def __init__(self, data, block_size):
        self.data = data
        self.block_size = block_size
    
    def __len__(self):
        return len(self.data) - self.block_size
    
    def __getitem__(self, idx):
        x = torch.tensor(self.data[idx:idx + self.block_size], dtype=torch.long)
        y = torch.tensor(self.data[idx + 1:idx + self.block_size + 1], dtype=torch.long)
        return x, y

# Model
class TransformerBlock(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.ln1 = nn.LayerNorm(config.n_embd)
        self.attn = nn.MultiheadAttention(
            embed_dim=config.n_embd,
            num_heads=config.n_head,
            dropout=config.dropout,
            batch_first=True
        )
        self.ln2 = nn.LayerNorm(config.n_embd)
        self.mlp = nn.Sequential(
            nn.Linear(config.n_embd, 4 * config.n_embd),
            nn.GELU(),
            nn.Linear(4 * config.n_embd, config.n_embd),
            nn.Dropout(config.dropout),
        )
    
    def forward(self, x):
        # Self-attention with causal mask
        x_norm = self.ln1(x)
        attn_out, _ = self.attn(
            x_norm, x_norm, x_norm,
            need_weights=False,
            is_causal=True
        )
        x = x + attn_out
        
        # Feed-forward
        x = x + self.mlp(self.ln2(x))
        return x

class GPT(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        self.token_embedding = nn.Embedding(config.vocab_size, config.n_embd)
        self.position_embedding = nn.Embedding(config.block_size, config.n_embd)
        self.blocks = nn.Sequential(*[TransformerBlock(config) for _ in range(config.n_layer)])
        self.ln_f = nn.LayerNorm(config.n_embd)
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size)
        
        self.apply(self._init_weights)
    
    def _init_weights(self, module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            module.weight.data.normal_(mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                module.bias.data.zero_()
    
    def forward(self, idx, targets=None):
        B, T = idx.shape
        
        # Embeddings
        tok_emb = self.token_embedding(idx)
        pos_emb = self.position_embedding(torch.arange(T, device=idx.device))
        x = tok_emb + pos_emb
        
        # Transformer blocks
        x = self.blocks(x)
        x = self.ln_f(x)
        logits = self.lm_head(x)
        
        # Loss
        loss = None
        if targets is not None:
            loss = F.cross_entropy(
                logits.view(-1, logits.size(-1)), 
                targets.view(-1)
            )
        
        return logits, loss
    
    @torch.no_grad()
    def generate(self, idx, max_new_tokens, temperature=1.0, top_k=None):
        """Generate text with temperature and top-k sampling"""
        for _ in range(max_new_tokens):
            # Crop context to block_size
            idx_cond = idx[:, -self.config.block_size:]
            
            # Get predictions
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / temperature
            
            # Optional top-k sampling
            if top_k is not None:
                v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = -float('inf')
            
            # Sample
            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
            idx = torch.cat((idx, idx_next), dim=1)
        
        return idx

# Training function
def train(config, text_file):
    # Load and prepare data
    print(f"Loading {text_file}...")
    with open(text_file, 'r', encoding='utf-8') as f:
        text = f.read()
    print(f"Text length: {len(text):,} characters")
    
    # Create tokenizer
    tokenizer = CharTokenizer(text)
    config.vocab_size = tokenizer.vocab_size
    print(f"Vocabulary size: {config.vocab_size}")
    
    # Encode data
    data = tokenizer.encode(text)
    n = int(0.9 * len(data))
    train_data = data[:n]
    val_data = data[n:]
    
    # Create datasets
    train_dataset = TextDataset(train_data, config.block_size)
    train_loader = DataLoader(train_dataset, batch_size=config.batch_size, shuffle=True)
    
    # Create model
    model = GPT(config).to(config.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    
    n_params = sum(p.numel() for p in model.parameters()) / 1e6
    print(f"Model parameters: {n_params:.2f}M")
    
    # Training loop
    print("\nTraining...")
    model.train()
    
    data_iter = iter(train_loader)
    for iter_num in range(config.max_iters):
        # Get batch
        try:
            X, Y = next(data_iter)
        except StopIteration:
            data_iter = iter(train_loader)
            X, Y = next(data_iter)
        
        X, Y = X.to(config.device), Y.to(config.device)
        
        # Forward pass
        logits, loss = model(X, Y)
        
        # Backward pass
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        
        # Logging
        if iter_num % config.eval_interval == 0:
            print(f"Step {iter_num:4d} | Loss: {loss.item():.4f}")
    
    # Save model
    checkpoint = {
        'model_state_dict': model.state_dict(),
        'config': config,
        'tokenizer': tokenizer,
    }
    torch.save(checkpoint, 'model.pt')
    print(f"\nModel saved to model.pt")
    
    return model, tokenizer

# Inference function
def inference(checkpoint_path, prompt="", max_new_tokens=200, temperature=0.8, top_k=50):
    # Load checkpoint
    print(f"Loading model from {checkpoint_path}...")
    checkpoint = torch.load(checkpoint_path, map_location='cpu')
    
    config = checkpoint['config']
    tokenizer = checkpoint['tokenizer']
    
    # Create and load model
    model = GPT(config).to(config.device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    # Prepare prompt
    if prompt:
        idx = torch.tensor([tokenizer.encode(prompt)], device=config.device)
    else:
        # Start with a random token
        idx = torch.zeros((1, 1), dtype=torch.long, device=config.device)
    
    print(f"\nGenerating text...")
    print("-" * 50)
    
    # Generate
    with torch.no_grad():
        generated = model.generate(idx, max_new_tokens, temperature, top_k)
        output = tokenizer.decode(generated[0].tolist())
    
    print(output)
    print("-" * 50)
    
    return output

# Main
def main():
    parser = argparse.ArgumentParser(description='Simple GPT Training/Inference')
    parser.add_argument('mode', choices=['train', 'inference'], help='Mode to run')
    parser.add_argument('--text-file', type=str, default='input.txt', help='Text file for training')
    parser.add_argument('--checkpoint', type=str, default='model.pt', help='Model checkpoint path')
    parser.add_argument('--prompt', type=str, default='', help='Prompt for generation')
    parser.add_argument('--max-tokens', type=int, default=200, help='Max tokens to generate')
    parser.add_argument('--temperature', type=float, default=0.8, help='Sampling temperature')
    parser.add_argument('--top-k', type=int, default=50, help='Top-k sampling')
    
    args = parser.parse_args()
    
    if args.mode == 'train':
        config = Config()
        train(config, args.text_file)
        
        # Generate sample after training
        print("\nGenerating sample...")
        inference(args.checkpoint, prompt="", max_new_tokens=200)
        
    else:  # inference
        inference(
            args.checkpoint,
            prompt=args.prompt,
            max_new_tokens=args.max_tokens,
            temperature=args.temperature,
            top_k=args.top_k
        )

if __name__ == '__main__':
    main()