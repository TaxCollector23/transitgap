def test_worker_responses_identify_worker_and_request_sequence(client):
    first = client.get('/health/live')
    second = client.get('/health')

    assert first.headers['x-transitgap-instance'] == second.headers['x-transitgap-instance']
    assert first.json()['instance_id'] == first.headers['x-transitgap-instance']
    assert int(second.headers['x-transitgap-request-number']) == int(first.headers['x-transitgap-request-number']) + 1
    assert first.headers['x-transitgap-request-id'] != second.headers['x-transitgap-request-id']
    assert second.json()['runtime']['uptime_seconds'] >= 0
