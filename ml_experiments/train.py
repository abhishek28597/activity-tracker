import torch
from torch.utils.data import DataLoader
import argparse
import os
import glob
from model import Config, CharTokenizer, TextDataset, GPT

def load_text_from_data_folder(data_folder='../data'):
    """Load and concatenate all .txt files from the data folder"""
    txt_files = glob.glob(os.path.join(data_folder, '*.txt'))
    
    if not txt_files:
        raise ValueError(f"No .txt files found in {data_folder}")
    
    print(f"Found {len(txt_files)} text file(s):")
    all_text = []
    for txt_file in txt_files:
        print(f"  - {os.path.basename(txt_file)}")
        with open(txt_file, 'r', encoding='utf-8') as f:
            text = f.read()
            all_text.append(text)
    
    # Concatenate all text with a separator
    combined_text = '\n\n'.join(all_text)
    return combined_text

def load_text_from_file(text_file, data_folder='../data'):
    """Load text from a specific file (can be relative to data folder or absolute path)"""
    # Check if it's an absolute path
    if os.path.isabs(text_file):
        file_path = text_file
    else:
        # Try relative to data folder first
        file_path = os.path.join(data_folder, text_file)
        # If not found, try as relative to current directory
        if not os.path.exists(file_path):
            file_path = text_file
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Text file not found: {text_file} (tried: {file_path})")
    
    print(f"Loading text from: {os.path.basename(file_path)}")
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    return text

# Training function
def train(config, data_folder='../data', output_path='model.pt', text_file=None):
    # Ensure models directory exists
    models_dir = os.path.join(os.path.dirname(__file__), 'models')
    os.makedirs(models_dir, exist_ok=True)
    
    # If output_path is just a filename, save it in models directory
    # If it's an absolute path or contains directory, use it as-is
    if not os.path.isabs(output_path) and os.path.dirname(output_path) == '':
        output_path = os.path.join(models_dir, output_path)
    
    # Load and prepare data
    if text_file:
        # Load from specific file
        text = load_text_from_file(text_file, data_folder)
    else:
        # Load from all txt files in data folder (default)
        print(f"Loading text files from {data_folder}...")
        text = load_text_from_data_folder(data_folder)
    
    print(f"Total text length: {len(text):,} characters")
    
    # Create tokenizer
    tokenizer = CharTokenizer(text)
    config.vocab_size = tokenizer.vocab_size
    print(f"Vocabulary size: {config.vocab_size}")
    
    # Encode data
    data = tokenizer.encode(text)
    n = int(0.9 * len(data))
    train_data = data[:n]
    val_data = data[n:]
    
    print(f"Train samples: {len(train_data):,}, Val samples: {len(val_data):,}")
    
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
    torch.save(checkpoint, output_path)
    print(f"\nModel saved to {output_path}")
    
    return model, tokenizer, output_path

# Main
def main():
    parser = argparse.ArgumentParser(description='Train GPT Model')
    parser.add_argument('--data-folder', type=str, default='../data', help='Folder containing .txt files for training')
    parser.add_argument('--text-file', type=str, default=None, help='Specific .txt file to train on (from data folder or absolute path). If not provided, aggregates all .txt files from data folder.')
    parser.add_argument('--output', type=str, default='model.pt', help='Output model checkpoint path')
    parser.add_argument('--max-iters', type=int, default=5000, help='Maximum training iterations')
    parser.add_argument('--batch-size', type=int, default=64, help='Batch size')
    parser.add_argument('--learning-rate', type=float, default=3e-4, help='Learning rate')
    
    args = parser.parse_args()
    
    config = Config()
    config.max_iters = args.max_iters
    config.batch_size = args.batch_size
    config.learning_rate = args.learning_rate
    
    _, _, saved_path = train(config, data_folder=args.data_folder, output_path=args.output, text_file=args.text_file)
    
    # Generate sample after training
    print("\nGenerating sample...")
    from infer import inference
    # Use just the filename for inference (it will look in models/ folder)
    inference(os.path.basename(saved_path), prompt="", max_new_tokens=200)

if __name__ == '__main__':
    main()
