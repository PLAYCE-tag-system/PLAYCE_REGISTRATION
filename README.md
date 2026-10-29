# PLAYCE QR 등록 화면

수신기가 직접 읽은 UHF RFID 태그를 등록 챌린지에 연결하고 QR 코드를 표시하는 소스입니다.

## 파일

- `registration_reader.py`: 태그 이벤트를 받아 등록 서버에 챌린지 요청
- `qr-display/qr_server.py`: QR 화면용 웹 서버
- `qr-display/qr.html`, `qr-display/fonts/`: QR 화면과 폰트
- `.env.example`: 비밀 값이 없는 설정 예시

## 필요한 서비스

QR 코드는 태그 이벤트를 받기 위해 별도 [PLAYCE_READER_NETWORK 저장소](https://github.com/PLAYCE-tag-system/PLAYCE_READER_NETWORK)의 `pc/collector.py`가 `http://127.0.0.1:8765/`에서 실행 중이어야 합니다. 챌린지 발급에는 별도 등록 백엔드도 필요합니다. 등록 백엔드의 소스와 데이터베이스는 이 저장소에 없습니다.

## 실행

1. `.env.example`을 `.env`로 복사하고 실제 등록 API 주소, 내부 토큰, QR 클레임 URL 스킴을 설정하세요. `.env`는 Git에서 제외됩니다.
2. `python -m pip install -r qr-display/requirements.txt`로 QR 의존성을 설치하세요.
3. 태그 수집기를 켠 상태에서 `python registration_reader.py`를 실행하세요.
4. QR 서버를 켜기 전에 QR 서버 프로세스에도 같은 등록 API 주소를 설정하세요. 예: PowerShell에서 `$env:REGISTRATION_API_BASE = 'http://your-server:4300'`를 입력한 뒤 `python qr-display/qr_server.py`를 실행합니다.
5. `http://127.0.0.1:5173/qr.html`을 여세요.

실제 API 토큰, 태그 이력 및 로그는 포함하지 않았습니다.
