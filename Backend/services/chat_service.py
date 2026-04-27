class ChatService:
    def __init__(self):
        # 나중에 여기에 DB 세션이나 API 키 설정을 넣습니다.
        pass

    async def get_mock_response(self, user_message: str) -> str:
        # 현재는 실험 중이므로 고정된 Mock 데이터 반환
        return f"실험 중인 모델의 가짜 응답입니다: '{user_message}'에 대해 분석 중입니다."