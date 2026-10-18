"""Classify transport observations without guessing who closed a connection."""
def classify_provider_error(code):
    value=str(code or '')
    if 'http_403' in value:
        return {'stage':'access_denied','certainty':'origin_unconfirmed','reason':'접근 거부 응답; 키·도메인·서비스 또는 네트워크 정책 중 원인 미확정'}
    if any(x in value for x in ('INCORRECT_KEY','INVALID_KEY','EXPIRE_KEY','UNAVAILABLE_KEY','http_401')):
        return {'stage':'authentication_configuration','certainty':'error_class_confirmed','reason':'키·도메인·허용 범위 확인 필요'}
    if any(x in value for x in ('PARAM_REQUIRED','INVALID_REQUEST','INVALID_TYPE','INVALID_CRS','INVALID_FORMAT')):
        return {'stage':'request_format','certainty':'error_class_confirmed','reason':'공식 오류 코드에 따른 요청 형식 확인 필요'}
    if any(x in value for x in ('http_502','http_503','http_504')):
        return {'stage':'upstream_http_failure','certainty':'origin_unconfirmed','reason':'서비스·중간 게이트웨이·네트워크 정책 중 발생 위치 미확정'}
    if any(x in value for x in ('RemoteDisconnected','transport_error','network_error','ConnectionReset','Timeout')):
        return {'stage':'transport_failure','certainty':'origin_unconfirmed','reason':'인증 응답 수신 전 연결 실패; 인증 오류로 단정 불가'}
    return {'stage':'response_or_data','certainty':'requires_response_evidence','reason':'응답 형식 또는 결과 없음 확인 필요'}
