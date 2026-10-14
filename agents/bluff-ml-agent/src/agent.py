"""Fail-fast CUDA participant with SDK lifecycle and JSON checkpoints."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import torch
from bluff_agent.adapter import run_agent, log
from model import make_model
from gpu_budget import configure_gpu_memory

MODEL = None
RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')

def initialize(message):
    global MODEL
    torch.set_num_threads(1)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is required for this verification agent; CPU fallback is forbidden')
    configure_gpu_memory(torch)
    weights = Path(__file__).resolve().parents[1] / 'models' / 'policy.pt'
    MODEL = make_model()
    MODEL.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
    MODEL = MODEL.eval().to('cuda:0')
    with torch.inference_mode():
        test = torch.randn(128, 128, device='cuda:0')
        result = test @ test.T
        prediction = MODEL(torch.zeros(1, 6, device='cuda:0'))
        torch.cuda.synchronize()
        assert result.is_cuda and prediction.is_cuda and torch.isfinite(result).all()
    state = {'device': 'cuda:0', 'gpu_name': torch.cuda.get_device_name(0),
             'torch': torch.__version__, 'cuda': torch.version.cuda,
             'weights_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
             'cuda_self_test': True, 'inferences': 0}
    log(json.dumps(state))
    return state

def select_action(obs, checkpoint):
    state = dict(checkpoint)
    claim = obs.get('pending_claim') or {}
    decks = obs['game_config']['decks']
    held = sum(c['rank'] == claim.get('claimed_rank') for c in obs['hand'])
    features = [claim.get('count', 0) / 4, held / (4 * decks),
                obs.get('pile_size', 0) / (52 * decks), 0,
                len(obs['hand']) / (52 * decks), float(bool(claim.get('provisional_finish')))]
    with torch.inference_mode():
        prediction = MODEL(torch.tensor([features], device='cuda:0')).sigmoid()
        assert prediction.is_cuda
        probability = prediction.item()
    state['inferences'] += 1
    state['last_probability'] = probability
    if obs['phase'] == 'CHALLENGE':
        impossible = claim['count'] > 4 * decks - held
        return {'type': 'challenge' if impossible or probability > .8 else 'accept'}, state
    groups = defaultdict(list)
    for card in obs['hand']:
        groups[card['rank']].append(card)
    rank, cards = max(groups.items(), key=lambda item: (len(item[1]), -RANKS.index(item[0])))
    return {'type': 'place', 'card_refs': [c['card_ref'] for c in cards[:4]],
            'claimed_rank': rank}, state

if __name__ == '__main__':
    run_agent(select_action, on_initialize=initialize)
