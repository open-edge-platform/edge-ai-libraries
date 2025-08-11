# FAQ: Document Summarization Application

## Q: What file formats are supported?
A: PDF, docx and TXT (plain-text) files are supported.

## Q: How large can my document be?
A: The maximum file size may vary depending on the summarization model being used.

## Q: Can I use my own summarization model?
A: Yes, update the model files and configuration in the  OpenVINO™ model server service.

## Q: Where are summaries stored?
A: Summaries are not stored by default; they are returned in the response.

## Q: How do I update environment variables?
A: Edit the `.env` file in the project root and restart the services.

## Q: What is the ideal time for services or pods to become ready when deployed via Helm?
A: The typical initialization time for services and pods deployed using Helm is approximately 6 to 8 minutes, depending on the system resources and network conditions.

## Q: What should be done if the OVMS service deployed via Helm remains stuck in the init phase for more than 10 minutes?
A: If the OVMS pod does not proceed beyond the init phase within 10 minutes, consider the following debugging steps:

- ### Check Init Script Logs:
  Identify the exact command where the init container is stuck by inspecting its logs:

  `kubectl logs -n <your-namespace> <pod-name> -c init-script`

- ### Clean Up Persistent Volume Claims (PVCs):
  When `Values.global.keeppvc` in **values.yaml** is set to false, the PVC is expected to be deleted automatically when the Helm release is uninstalled. However, in some cases — especially when a deployment gets stuck or fails — the PVC might not be removed. Stale PVCs can cause issues during future deployments.

  Follow the steps below to clean up PVCs:

  - Uninstall the Helm release to allow Helm to delete any associated PVCs:

    `helm uninstall <release-name> -n <your-namespace>`

  - Then delete any leftover PVCs (if not auto-deleted):

    `kubectl get pvc -n <your-namespace>`

    `kubectl delete pvc <pvc-name> -n <your-namespace>`

  After PVC cleanup, try redeploying the service.

- ### Verify Network Stability:
  Ensure there are no underlying hardware issues such as a faulty network cable or unstable network connectivity, which might cause timeouts during initialization.
  
