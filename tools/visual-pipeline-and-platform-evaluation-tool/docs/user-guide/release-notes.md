<!--
# How to Use This Template

1. **Purpose**:
   - Summarize new features, improvements, bug fixes, and known issues for each release.
   - Help developers quickly understand updates and adapt workflows accordingly.

2. **Content Customization**:
   - Replace placeholders (e.g., `[Version X.X.X]`, `[YYYY-MM-DD]`, `<description>`) with specific release details.
   - Refer to the user stories in comments to understand what information developers expect to find.

3. **Style Guidelines**:
   - Use bullet points and concise descriptions for clarity.
   - Organize changes by category: New Features, Improvements, Bug Fixes, and Known Issues.
   - Use active voice and developer-focused language.
   - Follow the **Microsoft Developer Writing Style Guide**.

4. **GitHub Copilot Can Help**:
   - **For Style Adherence**:
     - This template specifys the style guide to be followed, ask Copilot to check.
     - Copilot can generate suggestions in line with the specified writing style.
   - **To Validate Content Completeness**:
     - The template includes in comments the user stories and acceptance criteria to be fulfilled by its content in each section. Copilot can check if you included all required information.
5. **Validation**:
   - Verify all details, links, and formatting before publishing.
   - Ensure that descriptions are accurate and actionable.

-->

# Release Notes

Details about the changes, improvements, and known issues in this release of the application.

## Current Release: [Version 1.0.0]
**Release Date**: [2025-03-31]

### New Features
<!--
**Guidelines for New Features**:
1. **What to Include**:
   - Summarize new capabilities introduced in this release.
   - Highlight how these features help developers or solve common challenges.
   - Link to relevant guides or instructions for using the feature.
2. **Example**:
   - **Feature**: Added multi-camera configuration support.
     - **Benefit**: Enables developers to monitor larger areas in real-time.
     - [Learn More](./how-to-customize.md)
-->

- **Feature 1**: Pre-trained Models Optimized for Specific Use Cases: ViPPET includes pre-trained models that are optimized for specific use cases, such as object detection for Smart NVR pipeline. These models can be easily integrated into the pipeline, allowing users to quickly evaluate their performance on different Intel platforms.
- **Feature 2**: Metrics Collection with Turbostat and Qmassa: VIPPET collects real-time CPU and GPU performance metrics using Turbostat and Qumasa. The collector agent runs in a dedicated collector container, gathering CPU and GPU metrics. Users can access and analyze these metrics via inutiative UI, enabling efficient system monitoring and optimization.
- **Feature 3**: Smart NVR Pipeline Integration: The Smart NVR Proxy Pipeline is seamlessly integrated into the tool, providing a structured video recorder architecture. It enables video analytics by supporting AI inference on selected input channels while maintaining efficient media processing. The pipeline includes multi-view composition, media encoding, and metadata extraction for insights.



### Known Issues

- **Issue**: The VIPPET container fails to start the analysis when the "Run" button is clicked in the UI, specifically for systems without GPU.
  - **Workaround**: Consider upgrading the hardware to meet the required specifications for optimal performance.

