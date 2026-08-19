"""프로젝트 루트를 sys.path에 올려 `from src...` 임포트가 어디서 pytest를 실행하든 동작하게 한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
