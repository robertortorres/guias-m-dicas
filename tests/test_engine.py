import sys,unittest
sys.path.insert(0,'app')
from engine import fields,suggest,filename,validate
class Tests(unittest.TestCase):
 def test_fields(self):
  f=fields('GUIA DE CONSULTA\n2 - Nº Guia no Prestador 374896042026\n7 - Nome\nANA CATARINA DE ALMEIDA VIEIRA')
  self.assertEqual(f['number'],'374896042026');self.assertEqual(f['name'],'ANA CATARINA DE ALMEIDA VIEIRA');self.assertEqual(f['kind'],'guia')
 def test_group(self):
  p=[dict(page=i+1,kind=k,number='12',name='Ana Vieira') for i,k in enumerate(['guia','pedido','laudo','guia'])]
  self.assertEqual(suggest(p,'reports')[0]['pages'],[1,2,3]);self.assertEqual(len(suggest(p,'guides')),4)
 def test_names(self):
  self.assertEqual(filename({'number':'12','name':'Ana de Almeida Vieira'},'orders'),'12 Pedido Médico Ana Vieira.pdf')
 def test_coverage(self):
  g={'number':'12','name':'Ana Vieira','pages':[1,2],'approved':True}
  validate([g],2)
  with self.assertRaises(ValueError):validate([g,g],2)
  g['pages']=[1]
  with self.assertRaises(ValueError):validate([g],2)
if __name__=='__main__':unittest.main()
