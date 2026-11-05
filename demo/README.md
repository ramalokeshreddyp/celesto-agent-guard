## Demo Video

The demo video (`walkthrough.mp4`) is not included in the repository due to file size.

**What it shows (3 minutes):**
1. `docker compose up --build` — both services become healthy within 60s
2. `GET /health` → `{"status": "ok"}`
3. `GET /api/runs` → shows seeded `sbx-seeddemo1` row
4. Running `python -m agent.eval_runner` — 20 fresh sandbox runs complete
5. A malicious fork-bomb submission being detected by safety hook
6. The exfiltration attempt being blocked (command log shows `decision=block`)
7. `python -m pytest tests/ -v` — all tests pass

**To record your own walkthrough:**
```bash
# Start the stack
docker compose up --build -d

# Record terminal session (e.g., with asciinema)
asciinema rec demo/walkthrough.cast

# Run the eval
python -m agent.eval_runner

# Run tests
python -m pytest tests/ -v
```
