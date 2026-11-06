"""Ejecuta todas las celdas con un kernel Jupyter y guarda sus salidas reales."""
from pathlib import Path
import os,sys,json,time,argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('notebook',nargs='?',type=Path)
args=parser.parse_args()
path=args.notebook.resolve() if args.notebook else Path(__file__).resolve().parent/'NS4DA_Desarrollo_carga_aerea_2025.ipynb'
ROOT=path.parent
for key,folder in [('IPYTHONDIR','.ipython'),('MPLCONFIGDIR','.matplotlib'),('JUPYTER_PATH','.jupyter'),('JUPYTER_CONFIG_DIR','.jupyter/config'),('JUPYTER_RUNTIME_DIR','.jupyter/runtime')]:
 os.environ[key]=str(ROOT/folder)
 (ROOT/folder).mkdir(parents=True,exist_ok=True)
spec=ROOT/'.jupyter/kernels/carga2025';spec.mkdir(parents=True,exist_ok=True)
(spec/'kernel.json').write_text(json.dumps({'argv':[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}'],'display_name':'Carga2025','language':'python'}))
import nbformat
from nbclient import NotebookClient
nb=nbformat.read(path,as_version=4)
nb.metadata['execution']={'runner':'Jupyter / nbclient','all_cells_passed':False,'status':'running'}
nbformat.write(nb,path)
client=NotebookClient(nb,timeout=600,kernel_name='carga2025',resources={'metadata':{'path':str(ROOT)}})
t=time.perf_counter()
try:
 client.execute()
 nb.metadata['execution']={'runner':'Jupyter / nbclient','elapsed_seconds':round(time.perf_counter()-t,2),'code_cells_executed':sum(c.cell_type=='code' for c in nb.cells),'all_cells_passed':True,'status':'complete'}
except BaseException as error:
 nb.metadata['execution'].update(status='failed',error_type=type(error).__name__,all_cells_passed=False)
 raise
finally:
 nbformat.write(nb,path)
print('NOTEBOOK COMPLETO',dict(nb.metadata['execution']),flush=True)
