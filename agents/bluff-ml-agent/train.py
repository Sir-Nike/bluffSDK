"""Build-time CPU training on synthetic claims; no competition training data."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'src'))
import torch
from model import make_model

torch.set_num_threads(1)
torch.manual_seed(42)
model = make_model()
optimizer = torch.optim.Adam(model.parameters(), lr=.02)
x = torch.rand(4096, 6)
# A synthetic teacher, solely for verifying model packaging/inference.
y = ((x[:, 0] + x[:, 1] > 1.0) | ((x[:, 5] > .8) & (x[:, 2] < .2))).float().unsqueeze(1)
for _ in range(200):
    logits = model(x)
    loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, y)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
Path('models').mkdir(exist_ok=True)
torch.save(model.state_dict(), 'models/policy.pt')
metrics = {'seed': 42, 'samples': len(x), 'steps': 200, 'loss': float(loss.detach()),
           'training_accuracy': float(((model(x) > 0) == y.bool()).float().mean()),
           'purpose': 'synthetic CUDA integration fixture, not competitive evaluation'}
Path('models/training.json').write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics))
