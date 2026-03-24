from app import create_app
app = create_app('development')

with app.test_client() as client:
    r = client.get('/')
    print('GET / status:', r.status_code)
    if r.status_code == 200:
        print('Response snippet:', r.data[:80])
