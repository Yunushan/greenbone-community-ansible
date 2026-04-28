# Contributing

Contributions are welcome.

## Local checks

```bash
python3 -m pip install --user ansible-core ansible-lint yamllint
ansible-galaxy collection install -r requirements.yml
ansible-lint
yamllint .
```

## Guidelines

- Keep default installation single-master.
- Keep Docker mode portable across the supported distributions.
- Do not commit generated secrets or inventory credentials.
- Document any distribution-specific behavior in `docs/troubleshooting.md`.
