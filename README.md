This project represents a template for a deployment system using fabric3.

https://pypi.org/project/Fabric3/

To use it you first need to install this template module
into the desired python environment using:

```
pip install git+https://github.com/ICRAR/fabfileTemplate
```

You can directly run installations with this template, but the intentional
usage of this package is to provide a standardised and flexible installation
procedure for other systems for operational or development deployments on
the cloud and on dedicated computers. By using fabric3 as a backend this 
template also enables parallel installations on many computers.

Start by copying the whole fabfile directory from the fabfileTemplate into
your projects top level directory. Then edit the file fabfile/APPspecific.py
