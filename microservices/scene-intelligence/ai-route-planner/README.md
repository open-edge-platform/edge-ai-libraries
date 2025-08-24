# Route Planner - Agentic AI based Commuter Support System

A sophisticated Gradio-based web application that demonstrates dynamic route planning using agentic AI. The application integrates real GPX route data with multiple simulated data sources (weather, traffic, forest fire alerts) to determine optimal routes with a comprehensive visual thinking process.

## Features

- **Interactive Web Interface**: Modern Gradio-based UI with progressive web app (PWA) support
- **Real GPX Route Integration**: Uses actual GPX files with waypoints and track data for realistic route visualization
- **Agentic AI Thinking Process**: Comprehensive visual representation of the AI agent's decision-making process
- **Multiple Data Sources**: Simulated MCP (Model Context Protocol) servers for:
  - Weather conditions analysis
  - Traffic congestion and incident detection
  - Forest fire alerts and environmental hazards
- **Dynamic Route Switching**: Automatically overlays alternative routes based on detected conditions
- **Real-time Progress Visualization**: Multi-step progress tracking with detailed thinking output
- **Advanced Map Integration**: Folium-based maps with multiple route overlays, markers, and route information
- **Modular Architecture**: Clean separation of concerns with services, utilities, and data models
- **Comprehensive Logging**: Full application logging with configurable levels

## Project Structure

```
commute_agent/
├── main.py                    # Main Gradio application entry point
├── config.py                 # Application configuration settings
├── constants.py              # Application constants and mappings
├── models.py                 # Data models and classes
├── LICENSE                   # Project license
├── agents/                   # AI agent logic
│   └── route_agent.py        # Core agentic routing logic with thinking process
├── data/                     # Mock MCP servers
│   ├── weather_mcp.py        # Weather data simulation
│   ├── traffic_mcp.py        # Traffic congestion simulation
│   └── forest_fire_mcp.py    # Forest fire alerts simulation
├── services/                 # Business logic services
│   └── route_service.py      # Route management and GPX integration
├── utils/                    # Utility modules
│   ├── gpx_parser.py         # GPX file parsing and processing
│   ├── location_manager.py   # Location coordinate management
│   ├── logging_config.py     # Logging configuration
│   └── map_creator.py        # Map creation and visualization
├── gpx/                      # Route data files
│   ├── route_main.gpx        # Primary route with waypoints
│   ├── route_accident.gpx    # Alternative route for traffic incidents
│   └── route_fire.gpx        # Alternative route for fire hazards
├── README.md                 # This documentation
└── todo.md                   # Development progress tracking
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd commute_agent
   ```

2. **Install required dependencies**:
   ```bash
   pip install gradio folium
   ```

3. **Verify GPX files** (optional):
   ```bash
   ls gpx/
   # Should show: route_main.gpx, route_accident.gpx, route_fire.gpx
   ```

## Usage

1. **Start the application**:
   ```bash
   python main.py
   ```
   
   The application will start on `http://localhost:7864` (configurable in `config.py`)

2. **Access the web interface**:
   - Open your web browser and navigate to `http://localhost:7864`
   - The application supports PWA (Progressive Web App) features

3. **Use the route planning interface**:
   - The application automatically loads locations from the GPX waypoints
   - Select "From" and "To" locations from the dropdown menus
   - Click "Find Route" to start the AI analysis
   - **Phase 1**: Immediate map display showing the main route from `route_main.gpx`
   - **Phase 2**: Watch the real-time AI thinking process with detailed analysis
   - **Phase 3**: View final route decisions with alternative routes overlaid if conditions detected
   - Examine the comprehensive route information including weather, traffic, and safety analysis

## Real GPX Route Integration

The application uses three pre-configured GPX files for realistic route visualization:

- **`route_main.gpx`**: Primary route loaded from actual GPS track data with waypoints
- **`route_accident.gpx`**: Alternative route displayed when traffic incidents are detected
- **`route_fire.gpx`**: Fire-safe alternative route shown when forest fire alerts are triggered

The system automatically extracts:
- **Waypoints**: Start/end locations with descriptions
- **Track Points**: Detailed GPS coordinates for accurate route visualization
- **Route Bounds**: Automatic map centering and zoom calculation

## How It Works

### Agentic AI Multi-Phase Process

The application demonstrates a sophisticated multi-phase agentic AI approach:

**Phase 1: Immediate Route Display**
- Instantly loads and displays the main route from `route_main.gpx`
- Provides immediate visual feedback while AI analysis begins

**Phase 2: Comprehensive Analysis**
1. **Analyzing weather conditions** - Retrieves weather data for the route corridor
2. **Checking road congestion** - Analyzes traffic patterns, incidents, and delays
3. **Scanning for forest fire alerts** - Checks for environmental hazards and fire risks
4. **Evaluating alternative routes** - Considers backup routes based on detected conditions
5. **Calculating optimal path** - Determines final route recommendation with reasoning

**Phase 3: Final Route Visualization**
- Overlays alternative routes if adverse conditions are detected
- Updates map with color-coded route options
- Provides comprehensive route information panel

### Advanced Route Decision Logic

The AI agent uses sophisticated decision-making criteria:

**Weather-Based Decisions**:
- Severe weather conditions (rainy, stormy, snowy) trigger safety considerations
- Wind speed analysis for vehicle stability
- Temperature factors for road conditions

**Traffic-Based Decisions**:
- Heavy or severe congestion levels trigger alternative route search
- Accident detection automatically displays `route_accident.gpx`
- Real-time delay estimation and route comparison

**Environmental Hazard Assessment**:
- High or extreme fire alert levels trigger `route_fire.gpx` display
- Road closure analysis due to environmental factors
- Safety corridor evaluation

### GPX Data Processing Pipeline

The system includes a comprehensive GPX processing pipeline:

1. **GPX Parsing** (`utils/gpx_parser.py`):
   - Extracts waypoints with descriptions and coordinates
   - Processes track points for detailed route visualization
   - Calculates route bounds for optimal map display

2. **Route Service Integration** (`services/route_service.py`):
   - Manages multiple GPX files and route switching
   - Coordinates map generation with route data
   - Handles fallback scenarios for missing data

3. **Map Creation** (`utils/map_creator.py`):
   - Creates interactive Folium maps with multiple layers
   - Adds color-coded route lines and markers
   - Generates route information overlays

## Architecture & Design Patterns

### Service-Oriented Architecture

The application follows clean architecture principles with clear separation of concerns:

- **Presentation Layer** (`main.py`): Gradio interface and user interaction
- **Service Layer** (`services/`): Business logic and route management
- **Data Layer** (`data/`): Mock MCP servers and data sources
- **Utility Layer** (`utils/`): Common functionality and helpers
- **Models** (`models.py`): Data structures and type definitions

### Configuration Management

- **`config.py`**: Centralized application configuration
- **`constants.py`**: Application-wide constants and mappings
- **Environment-specific settings**: Server ports, PWA configuration, logging levels

### Data Models

The application uses strongly-typed data models for reliability:

- **`WeatherData`**: Weather condition information
- **`TrafficData`**: Traffic and congestion details
- **`FireAlertData`**: Environmental hazard information
- **`RouteInfo`**: Complete route analysis results
- **`RoutePoints`**: Geographic coordinate management

## Deployment Options

### Local Development
```bash
python main.py
# Access at http://localhost:7864
```

### Production Deployment

**Docker Deployment**:
```bash
# Create Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 7864
CMD ["python", "main.py"]
```

**Cloud Platform Deployment**:
- **Hugging Face Spaces**: Upload as a Gradio Space
- **Railway/Heroku**: Deploy with container or buildpack
- **Google Cloud Run**: Containerized deployment with auto-scaling

**Configuration for Production**:
```python
# In config.py
SERVER_CONFIG = {
    "server_name": "0.0.0.0",
    "server_port": int(os.environ.get("PORT", 7864)),
    "share": False,
    "pwa": True
}
```

## Customization & Extension

### Adding New Data Sources

1. **Create a new MCP server** in the `data/` directory:
   ```python
   # data/new_data_source_mcp.py
   def get_new_data(location: str) -> dict:
       return {
           "location": location,
           "data_field": "value",
           # ... other fields
       }
   ```

2. **Create corresponding data model** in `models.py`:
   ```python
   @dataclass
   class NewDataSource:
       location: str
       data_field: str
       
       @classmethod
       def from_dict(cls, data: Dict[str, Any]) -> 'NewDataSource':
           return cls(
               location=data.get('location', ''),
               data_field=data.get('data_field', '')
           )
   ```

3. **Integrate in the route agent** (`agents/route_agent.py`):
   - Import the new MCP function
   - Add data retrieval call in `get_optimal_route()`
   - Update thinking steps and decision logic

### Adding New GPX Routes

1. **Add GPX file** to the `gpx/` directory
2. **Update constants.py**:
   ```python
   GPX_FILES = {
       'main': 'route_main.gpx',
       'accident': 'route_accident.gpx',
       'fire': 'route_fire.gpx',
       'new_route': 'route_new.gpx'  # Add new route
   }
   ```
3. **Update route logic** in `services/route_service.py` to handle the new route

### Customizing the User Interface

**Modify the Gradio Interface** (`main.py`):
```python
# Add new input components
with gr.Row():
    new_input = gr.Slider(
        minimum=0, maximum=100, 
        label="New Parameter"
    )

# Modify CSS styling
css = """
.custom-style {
    background-color: #f0f0f0;
    border-radius: 10px;
}
"""
```

**Enhance Map Visualization** (`utils/map_creator.py`):
- Add new map layers and overlays
- Customize marker styles and colors
- Include additional route information

### Configuration Customization

**Server Configuration** (`config.py`):
```python
SERVER_CONFIG = {
    "server_name": "0.0.0.0",
    "server_port": 8080,  # Custom port
    "share": True,        # Enable public sharing
    "pwa": True,         # PWA support
    "auth": ("username", "password")  # Add authentication
}
```

**Logging Configuration** (`utils/logging_config.py`):
- Adjust log levels for different modules
- Configure file output and rotation
- Add custom formatters

## Technical Architecture

### Core Technologies

- **Framework**: Gradio 4.x for modern web interface with PWA support
- **Mapping**: Folium for interactive map visualization with Leaflet.js backend
- **Backend**: Python with asyncio-compatible design patterns
- **Data Processing**: Custom GPX parsing with coordinate transformation
- **State Management**: Service-oriented architecture with dependency injection
- **Logging**: Comprehensive logging with configurable levels and outputs

### Key Algorithms

**Route Optimization Algorithm**:
- Multi-criteria decision analysis (MCDA) for route selection
- Weighted scoring system for different route factors
- Dynamic route switching based on real-time conditions

**GPX Processing Pipeline**:
- XML parsing with error handling and validation
- Coordinate system transformation and bounds calculation
- Route simplification for optimal map rendering

**Map Generation Algorithm**:
- Automatic zoom level calculation based on route bounds
- Dynamic marker placement with collision avoidance
- Progressive route loading for large datasets

### Performance Considerations

- **Lazy Loading**: GPX files loaded on-demand to reduce startup time
- **Caching Strategy**: Route calculations cached for repeated requests
- **Memory Management**: Efficient handling of large GPX files
- **Async Processing**: Non-blocking UI updates during AI analysis

## Testing & Quality Assurance

### Test Files

The project includes comprehensive testing utilities:

- **`test_logging.py`**: Logging system validation
- **`test_route_selection.py`**: Route selection algorithm testing

### Manual Testing Workflow

1. **Basic Functionality**:
   ```bash
   python main.py
   # Test route selection with different location combinations
   ```

2. **GPX Data Validation**:
   ```bash
   # Verify GPX files are properly formatted
   python -c "from utils.gpx_parser import parse_gpx_file; print(parse_gpx_file('gpx/route_main.gpx'))"
   ```

3. **Error Handling**:
   - Test with missing GPX files
   - Test with invalid location selections
   - Test network connectivity issues

### Debugging & Monitoring

**Application Logging**:
- Logs stored in `route_app.log`
- Configurable log levels via `utils/logging_config.py`
- Real-time monitoring of AI decision process

**Performance Monitoring**:
- Route generation timing analysis
- Memory usage tracking for large GPX files
- Map rendering performance metrics

## Future Enhancements & Roadmap

### Phase 1: Real Data Integration
- **Weather API Integration**: Replace mock weather data with OpenWeatherMap or similar services
- **Traffic API Integration**: Connect to Google Maps Traffic API or Waze data
- **Fire Alert Systems**: Integration with government fire alert APIs and satellite data
- **Event Calendar Integration**: RAG pipeline for calendar events affecting routes

### Phase 2: Advanced AI Features
- **Machine Learning Route Optimization**: Historical data analysis for route prediction
- **User Preference Learning**: Personalized route recommendations based on user behavior
- **Predictive Analytics**: Route condition forecasting using historical patterns
- **Natural Language Interface**: Chat-based route planning with conversational AI

### Phase 3: Enhanced Data Sources
- **Camera Data Integration**: Real-time traffic analysis from video feeds using VLM
- **SceneScape/Frigate Integration**: Live camera frame analysis for traffic conditions
- **IoT Sensor Integration**: Road condition sensors and environmental monitors
- **Social Media Integration**: Real-time event detection from social platforms

### Phase 4: Advanced Visualization
- **3D Route Visualization**: Terrain-aware route display with elevation profiles
- **Augmented Reality**: AR-based route guidance integration
- **Real-time Animation**: Live traffic flow visualization on routes
- **Multi-modal Transportation**: Integration of public transit, bike lanes, and walking paths

### Phase 5: Enterprise Features
- **Fleet Management**: Multi-vehicle route optimization
- **API Development**: RESTful API for third-party integrations
- **Analytics Dashboard**: Route performance metrics and usage analytics
- **Mobile App**: Native mobile application with offline capabilities

## Known Limitations & Workarounds

### Current Limitations

1. **Static Route Data**: Uses pre-generated GPX files instead of dynamic routing
   - **Workaround**: GPX files can be updated manually for different route scenarios

2. **Mock Data Sources**: Weather, traffic, and fire data are simulated
   - **Workaround**: Mock data designed to be easily replaceable with real APIs

3. **Limited Location Support**: Locations limited to GPX waypoints or predefined list
   - **Workaround**: Easy to extend location list in `constants.py`

4. **No Real-time Updates**: Route conditions don't update automatically
   - **Workaround**: Manual refresh triggers new analysis cycle

### Migration Path to Production

1. **Replace Mock MCPs**: Implement real API connections in `data/` directory
2. **Add Dynamic Routing**: Integrate with routing services like OSRM or GraphHopper
3. **Implement Caching**: Add Redis or similar for route and condition caching
4. **Add Authentication**: Implement user management and API rate limiting
5. **Database Integration**: Store route history and user preferences

## Contributing

### Development Setup

1. **Fork the repository** and create a feature branch
2. **Install development dependencies**:
   ```bash
   pip install -r requirements-dev.txt  # If available
   ```
3. **Run tests** before submitting changes:
   ```bash
   python test_logging.py
   python test_route_selection.py
   ```
4. **Follow code style guidelines**:
   - Use type hints for all functions
   - Add docstrings for public methods
   - Follow PEP 8 style guidelines

### Code Review Guidelines

- **Functionality**: Ensure new features don't break existing functionality
- **Performance**: Consider impact on map rendering and AI processing time
- **Documentation**: Update README and inline documentation
- **Testing**: Add appropriate test cases for new features

## License & Attribution

This project is provided as a demonstration of agentic AI concepts and modern web application architecture. It can be freely modified and extended for educational and commercial purposes under the terms specified in the LICENSE file.

### Third-party Libraries

- **Gradio**: BSD-3-Clause License
- **Folium**: MIT License
- **Python Standard Library**: PSF License

### Acknowledgments

- GPX route data processing inspired by GPS track analysis best practices
- Agentic AI thinking process design based on modern AI agent architectures
- Map visualization patterns following Leaflet.js and OpenStreetMap conventions

