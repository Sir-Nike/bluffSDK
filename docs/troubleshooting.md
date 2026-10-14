# Troubleshooting

`unknown card reference` means references were retained across observations.
`oversized checkpoint` means the serialized state exceeds 1 MiB. A timeout or
malformed response causes a legal fallback for that decision; later decisions
still return to the same agent.
