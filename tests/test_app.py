import unittest, tempfile
from pathlib import Path
import app.database as db
class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); db.DB_PATH=Path(cls.tmp.name)/'test.db'
        from app import create_app
        cls.client=create_app({'TESTING':True}).test_client()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_health_and_crud(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/api/meta').status_code,200)
        r=self.client.post('/api/projects',json={'name':'Test','description':'','output_currency':'EUR','target_year':2026})
        self.assertEqual(r.status_code,201)
        pid=r.get_json()['id']; self.assertEqual(self.client.get('/api/projects/'+pid).status_code,200)
if __name__=='__main__':unittest.main()
