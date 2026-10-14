"""SDK-only heuristic and random participants; checkpointed private RNG."""
import os
import random
import secrets
from collections import defaultdict
from bluff_agent.adapter import run_agent

RANKS = ('A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K')

def initialize(message):
    return {'seed': secrets.randbits(128), 'decisions': 0}

def select_action(obs, checkpoint):
    state = dict(checkpoint)
    rng = random.Random(state['seed'] + state['decisions'])
    state['decisions'] += 1
    if os.environ.get('BLUFF_POLICY', 'heuristic') == 'random':
        if obs['phase'] == 'CHALLENGE':
            return {'type': rng.choice(['accept', 'challenge'])}, state
        cards = rng.sample(obs['hand'], rng.randint(1, min(4, len(obs['hand']))))
        return {'type': 'place', 'card_refs': [c['card_ref'] for c in cards],
                'claimed_rank': rng.choice(RANKS)}, state
    if obs['phase'] == 'CHALLENGE':
        claim = obs['pending_claim']
        held = sum(c['rank'] == claim['claimed_rank'] for c in obs['hand'])
        impossible = claim['count'] > 4 * obs['game_config']['decks'] - held
        risky = obs['pile_size'] >= 10 and held == 0 and rng.random() < .35
        return {'type': 'challenge' if impossible or risky else 'accept'}, state
    groups = defaultdict(list)
    for card in obs['hand']:
        groups[card['rank']].append(card)
    rank, cards = max(groups.items(), key=lambda item: (len(item[1]), -RANKS.index(item[0])))
    return {'type': 'place', 'card_refs': [c['card_ref'] for c in cards[:4]],
            'claimed_rank': rank}, state

if __name__ == '__main__':
    run_agent(select_action, on_initialize=initialize)
