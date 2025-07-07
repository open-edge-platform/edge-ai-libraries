# How to Deploy with the Edge Manageability Framework

Edge Manageability Framework, part of Intel’s Open Edge Software, simplifies edge application deployment and management, making it easier to deploy edge solutions at scale. Edge Manageability Framework provides:

* **Secure Infrastructure Management**: Offers secure and efficient remote onboarding and management of your edge node fleet across sites and geographies. Zero-trust security configuration reduces the time required to secure your edge applications.

* **Deployment Orchestration and Automation**: Lets you roll out and update applications and configure infrastructure nodes across your network from a single pane of glass. Edge Manageability Framework provides automated cluster orchestration and dynamic application deployment.

* **Automated Deployment**: Automates the remote installation and updating of applications at scale.

* **Deep Telemetry**: Gives you policy-based Lifecycle management and centralized visibility into your distributed edge infrastructure and deployments.

* **Flexible Configuration**: From organizing your physical infrastructure to managing the permutations of executing applications in a variety of runtime environments,Edge Manageability Framework gives you flexibility to define the policies, criteria, and hierarchies that make the most sense for your specific business needs.

This section shows how to deploy the Document Summarization Sample Application on the Edge Management Framework.

## Steps to Deploy on Edge Manageability Framework

### Prerequisites

1. Able to access the Edge Manageability Framework web UI with one or more [edge nodes onboarded](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/set_up_edge_infra/edge_node_onboard.html>) to the Edge Manageability Framework.
1. Clusters with a [privilege template](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/additional_howtos/set_up_a_cluster_template.html>) were created on the needed edge nodes following the procedures described in [Create Cluster](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/set_up_edge_infra/create_clusters.html#create-clusters>).

### Make Available the Deployment Package

1. Clone the **Document Summarization repository**:

    ```bash
    git clone <repository-url>
    cd <repository-url>/sample-applications/document-summarization
    ```
    
   The official `repository-url` is `https://github.com/open-edge-platform/edge-ai-libraries`. For forked repos, ensure you use the right URL when cloning the repository.

2. From the Edge Manageability Framework web UI, import the Deployment Package in the **deployment-package** folder by following the steps described in [Import Deployment Package](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/package_software/import_deployment.html>).

3. After importing the deployment package into Edge Manageability Framework, you can see it in the list of Web UI:
   
    **![Document Summarization Image](./images/doc-sum-emf.png)** 

See [Deployment Packages](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/package_software/deploy_packages.html#deploy-packages>) for more information on deployment packages.

### Deploy the Application onto the Edge Nodes

To set up a deployment:

1. Click the Deployments tab on the top menu to see the Deployments page. On the Deployments page, you can see a list of created deployments. The status indicator shows a quick view of the status of the deployment, which depends on many factors.

1. Select Deployments tab and click the Setup a Deployment button. The Setup a Deployment page appears.

1. In the Setup a Deployment page, select the **document-summarization** package for the deployment from list, and click Next. The Select a Profile step appears:

1. In the Select a Profile step, select the deployment profile, and click Next. The Override Profile Values page appears.


1. The Override Profile Values page shows the deployment profile values that can be overridden. Provide the necessary overriding values, then click Next to proceed to the Select Deployment Type step.

1. In the Select Deployment Type page, select the type of deployment.

    1. If you select Automatic as the deployment type, enter the deployment name and metadata in the key-value format to select the target cluster.

    1. If you select Manual as the deployment type, enter the deployment name and select the clusters from the list of clusters.

1. Click Next to see the Review page.

1. Verify if the deployment details are correct, and click Deploy.

After a few minutes, the deployment will start and will take about 5 minutes to complete.

On the Edge Manageability Framework web UI, you can track the application installation through the [View Deployment Details](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/package_software/deployment_details.html#deployment-details>) page.

**Document Summarization** Sample Application is fully deployed when the application becomes green and the status is shown as _Running_.

You can view the deployment status on the Deployments page.

> Note:  If the deployment fails for any reason, the deployment status will display the “Error” or “Down” status.

For more information on setting up a deployment, see [Set up a Deployment](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/package_software/setup_deploy.html#setup-deploy>).

### Access the **Document Summarization** AI Suite

1. Download the kubeconfig file of the edge node cluster that contains the deployed application. See [Download Kubeconfig File](<https://docs.openedgeplatform.intel.com/edge-manage-docs/main/user_guide/set_up_edge_infra/accessing_clusters.html#accessing-clusters>)

2. Follow the steps described in the **Document Summarization** [Documentation](<deploy-with-helm.md>) according to the usage of the application.

> Note: Skip the Deploy Helm Chart step
