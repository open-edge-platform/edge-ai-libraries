## Todo List for Smart routing traffic Application

### Task1: Plan application architecture and create project structure
- [ ] Create project directory
- [ ] Outline the application structure (folders, files)
- [ ] Finalize the architecture of the application.

Opens

- How to show the route on the map
	- Use GPX files with preset routes to showcase the routes

- How many routes to cater.
	- depending on this we need to create multiple json files for the routes, 
		good route (1,2,3,4) based on the condition, bad route, preliminary route. 

### Task2: Implement mock MCP servers and data sources
- [ ] Create mock weather data source or use the weather MCP server (https://github.com/adhikasp/mcp-weather) 
- [ ] Get road congestion details from Camera Data MCP server
	- [ ] Data source from scenescape/frigate + VLM serving
	- [ ] When triggered the system will read few live frames from scenescape 
	- [ ] Send those frames to VLM with Prompt with function call
	- [ ] Read the output as GO/NOGO
- [ ] Create mock forest fire alerts data source or use live sources 
- [ ] Create event awareness mock server
	- [ ] Calendar events RAG pipeline 

### Task3: Build the agentic AI thinking system ( keep it generic as we could add more interfaces as plugin)
- [ ] Implement the core routing logic
- [ ] Integrate mock data sources
- [ ] Develop thinking process visualization
- [ ] Open -> How to select the route based on the thinking

### Task4: Create the Gradio interface with map visualization
- [ ] Design the Gradio UI (dropdowns, search button, thinking bar)
- [ ] Integrate the routing logic with the Gradio interface
- [ ] Implement map visualization
	- [ ]  Using preconfigured GPX or GeoJSON Files as per the thinking system

### Task5: Test and deploy the application
- [ ] Test the application locally
- [ ] Provide deployment instructions

### Task6: Deliver the completed application 
- [ ] Package the application
- [ ] Write documentation
- [ ] Present the final application