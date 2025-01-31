---
id: tethys_settings
title: Add Tethys Settings
sidebar_label: Add Tethys Settings
excerpt: "Add Tethys Settings to your app"
sidebar_position: 3
---

### Start from Previous Solution
If you wish to use the previous solution as a starting point:

```bash
git clone https://github.com/Aquaveo/tethysapp-workflows_tutorial.git
cd tethysapp-workflows_tutorial
git checkout -b new-app-setup-step new-app-setup-step-complete
```

### Add Settings

Next, you'll need to add some settings to your Tethys app to enable things like database and geoserver connections.

Begin by adding these imports to the top of your `app.py` file:

```python title="/tethysapp/workflows_tutorial/app.py"
from tethys_sdk.app_settings import PersistentStoreDatabaseSetting, SpatialDatasetServiceSetting, SchedulerSetting
```

Next, add the following code to your `app.py` file in your App class:

```python title="/tethysapp/workflows_tutorial/app.py"
class App(TethysAppBase):
    ...
    DATABASE_NAME = 'workflows_tutorial_db'
    SCHEDULER_NAME='primary_condor_scheduler'
    GEOSERVER_NAME='primary_geoserver'


    def persistent_store_settings(self):
        """
        Define persistent store settings.
        """
        ps_settings = (
            PersistentStoreDatabaseSetting(
                name=self.DATABASE_NAME,
                description='database for app to use.',
                initializer='workflows_tutorial.model.init_db',
                required=True,
                spatial=True
            ),
        )

        return ps_settings
    
    def spatial_dataset_service_settings(self):
        """
        Define spatial dataset service settings.
        """
        sds_settings = (
            SpatialDatasetServiceSetting(
                name=self.GEOSERVER_NAME,
                description='GeoServer service for app to use.',
                engine=SpatialDatasetServiceSetting.GEOSERVER,
                required=True,
            ),
        )

        return sds_settings
    

    def scheduler_settings(self):
        """
        Define scheduler settings
        """
        scheduler_settings = (
            SchedulerSetting(
                name=self.SCHEDULER_NAME,
                description='Scheduler for HTCondor cluster.',
                engine=SchedulerSetting.HTCONDOR,
                required=False,
            ),
        )

        return scheduler_settings
```

# Setup Services

### Condor Scheduler
First, you'll need to set up your HTCondor Scheduler
Begin by running this command to generate your condor SSH key

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/condor_key
```

When prompted, provide your ssh key with a pass phrase, and make note of that pass phrase. 

Next, go into your tethys admin settings in your tethys portal and navigate to the HTCondor Schedulers page. Press "Add HTCondor Scheduler"

Name this service 'condor_scheduler', and assign the 'Host' field the value of 'localhost'.

Update the username field to your username and the private key path to your personal condor_key file path, along with the private key pass that you provided when creating the key.

Finally, press "Save".
### GeoServer

First, initialize your GeoServer docker container by running:
```bash
    tethys docker init -c geoserver
```
Now start up your container by running
```bash 
    tethys docker start -c geoserver
```

Now, go to the "Site Admin" settings and find the "Tethys Services" section. Select the "Spatial Dataset Services" link.
Create a new Spatial Dataset Service named "primary_geoserver" of type GeoServer

Enter the endpoint and public endpoint as: http://localhost:8181/geoserver/rest/ if you're using Docker, or if you're using a default installation of GeoServer, use:  http://localhost:8080/geoserver/rest/

Fill out the username and password fields with "admin" as the username, and "geoserver" as the password

Press "Save".

### Persistent Store Service
Return to Site Admin, and go to the "Tethys Services" section, and then select the "Persistent Store Services" link.
Click "Add Persistent Store Service"

Give this new service the name "primary_db", with the following fields:
- 'Host': localhost
- 'Port': 5432
- 'Username': tethys_super
- 'Password': pass

Press "Save"

### Assign Services
Finally, go to your tethys app settings and add the settings you just created. 

Start by finding the section labeled `Persistent Store Database Settings' and click on the drop down under 'Persistent Store Service' and select 'primary_db'

Next, go to the 'Spatial Dataset Service Settings' section, and select 'geoserver' in the dropdown.

Lastly, move down to 'Scheduler Settings' and select 'condor_scheduler' in the dropdown.

### Solution

This concludes the Tethys Settings portion of the Tethys Workflows Extension Tutorial. You can view the solution on github at https://github.com/Aquaveo/tethysapp-workflows_tutorial or clone it as follows:

```bash
git clone https://github.com/Aquaveo/tethysapp-workflows_tutorial.git
cd tethysapp-workflows_tutorial
git checkout -b tethys-settings-step tethys-settings-step-complete
```




