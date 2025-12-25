---
id: app_setup
title: App Setup
sidebar_label: App Setup
excerpt: "Learn how to setup your new Tethys App"
sidebar_position: 2
---

### Create a New Tethys App
To begin working with the workflows extension, you'll need to setup a new app. To do this follow the steps on 
this page: [Creating a New App](https://docs.tethysplatform.org/en/stable/tutorials/key_concepts/new_app_project.html).

### Add Dependencies
Next, add some dependencies that will be required later in the tutorial. These packages provide functionality your workflow will utilize. Add these packages to the **requirements** section of your `install.yml` file of your app:

```yaml {6,8-10}
requirements:
  # Putting in a skip true param will skip the entire section. Ignoring the option will assume it be set to False
  skip: false
  conda:
    channels:
      - conda-forge
    packages:
      - gdal
      - pyproj
      - timezonefinder
```

You can install these packages manually with this command:
```bash
conda install -c conda-forge gdal pyproj timezonefinder
```

### Solution
This concludes the App Setup portion of the Tethys Workflows Extension Tutorial. You can view the solution on GitHub at https://github.com/Aquaveo/tethysapp-workflows_tutorial or clone it as follows:

```bash
git clone https://github.com/Aquaveo/tethysapp-workflows_tutorial.git
cd tethysapp-workflows_tutorial
git checkout -b new-app-setup-step new-app-setup-step-complete
```