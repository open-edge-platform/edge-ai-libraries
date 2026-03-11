# Deploy with Edge Orchestrator

Edge Orchestrator, part of Intel’s Edge Software, simplifies edge application deployment and management, making it easier to deploy edge solutions at scale. Edge Orchestrator provides:

- **Secure Infrastructure Management**: Offers secure and efficient remote onboarding and management of your edge node fleet across sites and geographies. Zero-trust security configuration reduces the time required to secure your edge applications.

- **Deployment Orchestration and Automation**: Lets you roll out and update applications and configure infrastructure nodes across your network from a single pane of glass. Edge Orchestrator provides automated cluster orchestration and dynamic application deployment.

- **Automated Deployment**: Automates the remote installation and updating of applications at scale.

- **Deep Telemetry**: Gives you policy-based life cycle management and centralized visibility into your distributed edge infrastructure and deployments.

- **Flexible Configuration**: From organizing your physical infrastructure to managing the permutations of executing applications in a variety of runtime environments, Edge Orchestrator gives you the flexibility to define the policies, criteria, and hierarchies that make the most sense for your specific business needs.

To deploy the **ChatQ&A** Application with the Edge Orchestrator, follow the steps described in this document.

## Procedure to Deploy with Edge Orchestrator

### Prerequisites

1. Access to the web interface of the Edge Orchestrator with one or more [Edge Nodes Onboarded](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/set_up_edge_infra/edge_node_onboard/index.html) to the Edge Orchestrator.

1. Clusters with a [privilege template](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/advanced_functionality/set_up_a_cluster_template.html) have been created on the needed Edge Nodes following the procedures described in [Create Cluster](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/set_up_edge_infra/clusters/create_clusters.html#create-cluster).

### Making the Deployment Package Available

1. Clone the **ChatQ&A** repository:

    ```bash
    # Clone the latest on mainline
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
    # Alternatively, Clone a specific release branch
    git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>

    cd edge-ai-libraries/sample-applications/chat-question-and-answer
    ```

    The official `repository-url` is `https://github.com/open-edge-platform/edge-ai-libraries`. In case of forked repos, please ensure the right url is used when cloning the repo.

1. From the web browser, open the URL of the Edge Orchestrator and import the Deployment Package present in the folder **deployment-package** following the steps described in [Import Deployment Package](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/package_software/import_deployment.html#import-deployment-package).

1. Once the deployment package has been imported into the Edge Orchestrator, you can see it in the list of Web UI as shown here.

    **![ChatQnA Image](../_assets/chatqna-emf.png)**

See [Deployment Packages](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/package_software/deploy_packages.html#view-deployment-packages) for more information on deployment packages.

### Deploy the Application onto the Edge Nodes

To set up a deployment:

1. Click the **Deployments** tab on the top menu to view the Deployments page. On the Deployments page, you can view the list of deployments that have been created. The status indicator shows a quick view of the status of the deployment, which depends on many factors.

1. Select the **Deployments** tab and click the **Setup a Deployment** button. The Setup a Deployment page appears.

1. On the Setup a Deployment page, select the **chatqna** package for the deployment from the list, and click **Next**. The Select a Profile step appears.

1. In the Select a Profile step, select the deployment profile, and click **Next**. The Override Profile Values page appears.

1. The Override Profile Values page shows the deployment profile values that are available for overriding. Provide the necessary overriding values, then click **Next** to proceed to the Select Deployment Type step.

1. On the Select Deployment Type page, select the type of deployment, and click **Next**:

    1. If you select **Automatic** as the deployment type, enter the deployment name and metadata in key-value format to select the target cluster.

    1. If you select **Manual** as the deployment type, enter the deployment name and select the clusters from the list of clusters.

1. Click **Next** to view the Review page.

1. Verify if the deployment details are correct and click **Deploy**.

After a few minutes, the deployment will start and will take about 5 minutes to complete.

In the Edge Orchestrator Web UI, you can track the application installation through the [View Deployment Details](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/package_software/deployment_details.html#view-deployment-details) view.

The **ChatQ&A** Sample Application is fully deployed when the applications become green and the status is shown as _Running_.

You can view the deployment status on the Deployments page.

> Note: If the deployment fails for any reason, the deployment status will display the “Error” or “Down” status.

For more information on setting up a deployment, see [Set up a Deployment](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/package_software/setup_deploy.html#set-up-a-deployment).

### Access the **ChatQ&A** AI-Suite

1. Download the kubeconfig of the cluster of the Edge Node on which the Application has been deployed. Refer [Kubeconfig Download](https://docs.openedgeplatform.intel.com/edge-manage-docs/dev/user_guide/set_up_edge_infra/clusters/accessing_clusters.html).

2. Follow the steps described in the **ChatQ&A** [Documentation](deploy-with-helm.md#step-6-verify-the-deployment) to proceed to using the application.
