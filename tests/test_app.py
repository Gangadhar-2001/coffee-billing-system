import os, tempfile, unittest

class BillingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.environ['DATABASE_PATH']=os.path.join(self.tmp.name,'test.db')
        os.environ['ADMIN_PASSWORD']='test-strong-password'
        import sys
        sys.modules.pop('app',None)
        from app import app
        self.app=app
        self.client=app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as s: self.token=s['csrf']
        self.client.post('/login',data={'csrf_token':self.token,'username':'admin','password':'test-strong-password'})
        with self.client.session_transaction() as s: self.token=s['csrf']
    def tearDown(self): self.tmp.cleanup()
    def test_checkout_and_invoice(self):
        r=self.client.post('/api/bills',json={'items':[{'id':1,'qty':2}],'discount':10,'payment':'UPI'},headers={'X-CSRF-Token':self.token})
        self.assertEqual(r.status_code,201)
        invoice=self.client.get(r.json['invoice_url'])
        self.assertIn(b'INVOICE #1',invoice.data)
        self.assertIn(b'178.50',invoice.data) # 180 - 10 + 5% GST
    def test_csrf(self):
        r=self.client.post('/api/bills',json={'items':[{'id':1,'qty':1}]})
        self.assertEqual(r.status_code,400)
    def test_reject_fake_price(self):
        r=self.client.post('/api/bills',json={'items':[{'id':1,'qty':1,'price':1}]},headers={'X-CSRF-Token':self.token})
        self.assertEqual(r.status_code,201)
        self.assertIn(b'94.50',self.client.get(r.json['invoice_url']).data)
if __name__=='__main__': unittest.main()
