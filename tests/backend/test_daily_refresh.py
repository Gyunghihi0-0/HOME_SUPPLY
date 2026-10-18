from copy import deepcopy
import json
from pathlib import Path
import subprocess
import pytest
import requests
from scripts.daily_refresh import refresh
from scripts.http_client import Client, SourceError
from scripts.geocoding import VWorld

ROOT = Path(__file__).resolve().parents[2]


def test_host_outage_is_not_retried_for_each_listing_but_other_sources_work(tmp_path):
    client = Client(cache_dir=tmp_path, pause=0)
    calls = []
    class Response:
        status_code = 200
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def iter_content(self, size):yield b'other official source'
    def request(method, url, **kwargs):
        calls.append(url)
        if 'api.vworld.kr' in url:
            raise requests.ConnectionError('simulated connection closed')
        return Response()
    client.session.request = request
    geo = VWorld(client, 'test-key', 'https://example.com/')
    for address in ('경기도 용인시 기흥구 동백동 1', '경기도 용인시 기흥구 동백동 2'):
        with pytest.raises(SourceError, match='vworld_network_error'):
            geo.locate(address)
    assert client.request('https://www.gg.go.kr/public') == b'other official source'
    assert len(calls) == 2


def test_timeout_preserves_records_and_does_not_claim_source_checks(tmp_path, monkeypatch):
    data = json.loads((ROOT/'contracts/example-latest.json').read_text(encoding='utf-8'))
    before = deepcopy(data)
    output = tmp_path/'latest.json'
    output.write_text(json.dumps(data), encoding='utf-8')
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired('pipeline', 540)
    monkeypatch.setattr(subprocess, 'run', timed_out)
    assert refresh(output) == 1
    after = json.loads(output.read_text(encoding='utf-8'))
    assert after['listings'] == before['listings']
    assert after['last_success_at'] == before['last_success_at']
    assert after['data_status'] == 'stale'
    assert all(s['status']=='not_checked' and s['error_code']=='daily_refresh_timeout' for s in after['sources'])


def test_vworld_failure_is_not_reported_as_molit_transport_failure(monkeypatch):
    from scripts.pipeline import enrich
    from scripts.replay_catalog import CapturedApplyhome
    from scripts.apis import empty_unit
    from tests.backend.test_enrichment import sample_notice, NOW
    capture = json.loads((ROOT/'tests/backend/fixtures/official-applyhome-2026-10-18.json').read_text(encoding='utf-8'))
    item = sample_notice()
    item.update(name='쌍용 더 플래티넘 한강',address='경기도 양평군 양서면 용담리 212-3번지 일원')
    item['units'] = [dict(empty_unit('84A', 84.9947), allocation_count=1)]
    monkeypatch.setenv('VWORLD_API_KEY', 'test-key')
    class BrokenGeo:
        def request(self, *args, **kwargs):raise SourceError('network_error')
    diagnostics = {}
    result = enrich([item],BrokenGeo(),NOW,dict(projects={},trade_locations={}),dict(version='test',approved=True),
                    None,'trade-test-key',apply_client=CapturedApplyhome(capture),diagnostics=diagnostics)
    assert result[5] == 'verified_target_location_required'
    assert {key:diagnostics[key] for key in ('vworld_error','geocoder','molit_requested')} == dict(vworld_error='vworld_network_error',geocoder='vworld',molit_requested=False)
    assert diagnostics['project_report']['records'][0]['coordinate_verified'] is False
    assert item['units'][0]['analysis_reason'] == 'verified_coordinates_missing'
