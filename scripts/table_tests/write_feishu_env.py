"""Write the user's Feishu credentials into backend/.env (gitignored).
Reads the values from environment so secrets don't appear in this script's source.
"""
import os
from pathlib import Path

app_id = os.environ["FEISHU_APP_ID"]
app_secret = os.environ["FEISHU_APP_SECRET"]
assert app_id.startswith("cli_"), f"unexpected app id format: {app_id[:8]}..."

env_path = Path(r'D:\one_agent\backend\.env')
text = env_path.read_text(encoding='utf-8') if env_path.exists() else ""

# Strip any prior FEISHU_* lines, then append fresh.
lines = [ln for ln in text.splitlines() if not ln.startswith('FEISHU_')]
addition = (
    f'FEISHU_ENABLED=true\n'
    f'FEISHU_APP_ID={app_id}\n'
    f'FEISHU_APP_SECRET={app_secret}\n'
    f'FEISHU_API_BASE=https://open.feishu.cn\n'
    f'FEISHU_SPACE_IDS=\n'
    f'FEISHU_SYNC_INTERVAL_MIN=15\n'
    f'FEISHU_PAGE_SIZE=50\n'
)
new_text = '\n'.join([ln for ln in lines if ln.strip()]) + '\n\n' + addition
env_path.write_text(new_text, encoding='utf-8')

# Verify .env is gitignored.
gi = Path(r'D:\one_agent\.gitignore').read_text(encoding='utf-8')
assert 'backend/.env' in gi, 'backend/.env is NOT gitignored!'
print('OK: credentials written to .env (gitignored)')
