import torch
import argparse
import os
import random
from model import GPT

# Inference function
def inference(checkpoint_path, prompt="", max_new_tokens=200, temperature=0.8, top_k=50):
    # If checkpoint_path is just a filename, look in models directory
    # If it's an absolute path or contains directory, use it as-is
    if not os.path.isabs(checkpoint_path) and os.path.dirname(checkpoint_path) == '':
        models_dir = os.path.join(os.path.dirname(__file__), 'models')
        checkpoint_path = os.path.join(models_dir, checkpoint_path)
    
    # Load checkpoint
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")
    
    print(f"Loading model from {checkpoint_path}...")
    # weights_only=False is safe here since we're loading our own checkpoints
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
    
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
        # Start with a random token from the vocabulary
        random_token = random.randint(0, config.vocab_size - 1)
        idx = torch.tensor([[random_token]], dtype=torch.long, device=config.device)
    
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
    parser = argparse.ArgumentParser(description='GPT Inference')
    parser.add_argument('--checkpoint', type=str, default='model.pt', help='Model checkpoint path (filename in models/ folder or full path)')
    parser.add_argument('--prompt', type=str, default='', help='Text prompt for generation (or use --text-file)')
    parser.add_argument('--text-file', type=str, default=None, help='Text file to use as prompt')
    parser.add_argument('--max-tokens', type=int, default=200, help='Max tokens to generate')
    parser.add_argument('--temperature', type=float, default=0.8, help='Sampling temperature')
    parser.add_argument('--top-k', type=int, default=50, help='Top-k sampling')
    
    args = parser.parse_args()
    
    # Determine prompt source
    prompt = args.prompt
    if args.text_file:
        if not os.path.exists(args.text_file):
            raise FileNotFoundError(f"Text file not found: {args.text_file}")
        print(f"Reading prompt from {args.text_file}...")
        with open(args.text_file, 'r', encoding='utf-8') as f:
            prompt = f.read()
    
    inference(
        args.checkpoint,
        prompt=prompt,
        max_new_tokens=args.max_tokens,
        temperature=args.temperature,
        top_k=args.top_k
    )

if __name__ == '__main__':
    main()
