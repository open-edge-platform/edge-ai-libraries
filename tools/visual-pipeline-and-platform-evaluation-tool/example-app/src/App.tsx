import { useState } from "react";
import {
  // Layout & surfaces
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Separator,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Skeleton,
  // Form
  Button,
  Input,
  Label,
  Badge,
  Switch,
  Checkbox,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Slider,
  RadioGroup,
  RadioGroupItem,
  Textarea,
  // Feedback
  Progress,
  ProgressTrack,
  ProgressIndicator,
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  // Dialogs
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  // Table
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  // Charts
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
  Area,
  AreaChart,
  CartesianGrid,
  XAxis,
  YAxis,
  // Icons
  Activity,
  Cpu,
  HardDrive,
  TrendingUp,
  Zap,
} from "@vippet/ui";

// --- Mock data for charts (ViPPET-style metrics) ---
const cpuData = Array.from({ length: 30 }, (_, i) => ({
  time: `${i}`,
  cpu: 30 + Math.sin(i * 0.3) * 20 + Math.random() * 10,
  gpu: 50 + Math.cos(i * 0.2) * 25 + Math.random() * 8,
  npu: 20 + Math.sin(i * 0.4) * 15 + Math.random() * 5,
}));

const benchmarkResults = [
  { pipeline: "person-detection", device: "CPU", fps: 42.3, streams: 4, status: "completed" },
  { pipeline: "vehicle-detection", device: "GPU", fps: 128.7, streams: 12, status: "completed" },
  { pipeline: "face-recognition", device: "NPU", fps: 95.1, streams: 8, status: "completed" },
  { pipeline: "action-recognition", device: "GPU", fps: 67.4, streams: 6, status: "running" },
  { pipeline: "anomaly-detection", device: "CPU", fps: 0, streams: 0, status: "failed" },
];

// --- Chart configs (ViPPET pattern) ---
const utilizationConfig: ChartConfig = {
  cpu: { label: "CPU", color: "var(--orange-chart)" },
  gpu: { label: "GPU", color: "var(--green-chart)" },
  npu: { label: "NPU", color: "var(--purple-chart)" },
};

export function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [sliderValue, setSliderValue] = useState([4]);
  const [selectedDevice, setSelectedDevice] = useState("");
  const [feedback, setFeedback] = useState("");

  return (
    <div className={darkMode ? "dark" : ""}>
      <div className="min-h-screen bg-background text-foreground p-8 transition-colors">
        <div className="mx-auto max-w-5xl space-y-8">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">@vippet/ui Example</h1>
              <p className="text-muted-foreground mt-1">
                Comprehensive showcase of the component library
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="dark-mode">Dark mode</Label>
              <Switch
                id="dark-mode"
                checked={darkMode}
                onCheckedChange={setDarkMode}
              />
            </div>
          </div>

          <Separator />

          <Tabs defaultValue="dashboard">
            <TabsList>
              <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
              <TabsTrigger value="components">Components</TabsTrigger>
              <TabsTrigger value="form">Form</TabsTrigger>
              <TabsTrigger value="data">Data Table</TabsTrigger>
            </TabsList>

            {/* ─── Dashboard Tab (ViPPET-style metrics) ─── */}
            <TabsContent value="dashboard" className="space-y-6 mt-4">
              {/* Summary cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {[
                  { label: "Avg FPS", value: "88.4", icon: Activity },
                  { label: "CPU Usage", value: "62%", icon: Cpu },
                  { label: "Active Streams", value: "30", icon: HardDrive },
                  { label: "Power Draw", value: "73W", icon: Zap },
                ].map((stat) => (
                  <Card key={stat.label}>
                    <CardContent className="pt-6">
                      <div className="flex items-center gap-3">
                        <div className="rounded-lg bg-primary/10 p-2">
                          <stat.icon className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground">
                            {stat.label}
                          </p>
                          <p className="text-2xl font-bold mt-1">{stat.value}</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Area chart — CPU/GPU/NPU utilization (ViPPET style) */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4" />
                    Device Utilization
                  </CardTitle>
                  <CardDescription>
                    CPU, GPU, and NPU usage over time (%)
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ChartContainer
                    config={utilizationConfig}
                    className="h-[250px] w-full"
                  >
                    <AreaChart data={cpuData}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        vertical={false}
                        stroke="#404040"
                        opacity={0.3}
                      />
                      <XAxis
                        dataKey="time"
                        tickLine={false}
                        axisLine={false}
                        tickMargin={9}
                        tickFormatter={(v) => `${v}s`}
                        stroke="#737373"
                      />
                      <YAxis
                        tickLine={false}
                        axisLine={false}
                        tickMargin={8}
                        domain={[0, 100]}
                        tickFormatter={(v) => `${v}%`}
                        width={50}
                        stroke="#737373"
                      />
                      <ChartTooltip
                        content={
                          <ChartTooltipContent
                            formatter={(value, name) => {
                              const label =
                                utilizationConfig[name as string]?.label || name;
                              return `${label}: ${Number(value).toFixed(1)}%`;
                            }}
                          />
                        }
                      />
                      <ChartLegend content={<ChartLegendContent />} />
                      <Area
                        type="monotone"
                        dataKey="cpu"
                        stroke="var(--orange-chart)"
                        fill="var(--orange-chart)"
                        fillOpacity={0.3}
                        strokeWidth={2.5}
                      />
                      <Area
                        type="monotone"
                        dataKey="gpu"
                        stroke="var(--green-chart)"
                        fill="var(--green-chart)"
                        fillOpacity={0.3}
                        strokeWidth={2.5}
                      />
                      <Area
                        type="monotone"
                        dataKey="npu"
                        stroke="var(--purple-chart)"
                        fill="var(--purple-chart)"
                        fillOpacity={0.3}
                        strokeWidth={2.5}
                      />
                    </AreaChart>
                  </ChartContainer>
                </CardContent>
              </Card>

              {/* System health */}
              <Card>
                <CardHeader>
                  <CardTitle>System Health</CardTitle>
                  <CardDescription>Current resource allocation</CardDescription>
                </CardHeader>
                  <CardContent className="space-y-5">
                    {[
                      { label: "CPU", value: 62 },
                      { label: "GPU", value: 88 },
                      { label: "Memory", value: 55 },
                      { label: "NPU", value: 40 },
                    ].map((metric) => (
                      <div key={metric.label} className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span>{metric.label}</span>
                          <span className="text-muted-foreground">
                            {metric.value}%
                          </span>
                        </div>
                        <Progress value={metric.value} max={100}>
                          <ProgressTrack>
                            <ProgressIndicator />
                          </ProgressTrack>
                        </Progress>
                      </div>
                    ))}
                  </CardContent>
                </Card>
            </TabsContent>

            {/* ─── Components Tab ─── */}
            <TabsContent value="components" className="space-y-6 mt-4">
              {/* Buttons */}
              <Card>
                <CardHeader>
                  <CardTitle>Buttons</CardTitle>
                  <CardDescription>
                    Various button variants and sizes
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap gap-3">
                    <Button>Default</Button>
                    <Button variant="secondary">Secondary</Button>
                    <Button variant="outline">Outline</Button>
                    <Button variant="ghost">Ghost</Button>
                    <Button variant="destructive">Destructive</Button>
                    <Button variant="link">Link</Button>
                  </div>
                  <Separator />
                  <div className="flex flex-wrap items-center gap-3">
                    <Button size="xs">Extra Small</Button>
                    <Button size="sm">Small</Button>
                    <Button size="default">Default</Button>
                    <Button size="lg">Large</Button>
                  </div>
                </CardContent>
              </Card>

              {/* Badges */}
              <Card>
                <CardHeader>
                  <CardTitle>Badges</CardTitle>
                  <CardDescription>Status indicators and labels</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-3">
                  <Badge>Default</Badge>
                  <Badge variant="secondary">Secondary</Badge>
                  <Badge variant="outline">Outline</Badge>
                  <Badge variant="destructive">Error</Badge>
                </CardContent>
              </Card>

              {/* Accordion */}
              <Card>
                <CardHeader>
                  <CardTitle>Accordion</CardTitle>
                  <CardDescription>Collapsible content sections</CardDescription>
                </CardHeader>
                <CardContent>
                  <Accordion type="single" collapsible>
                    <AccordionItem value="item-1">
                      <AccordionTrigger>
                        What hardware does ViPPET support?
                      </AccordionTrigger>
                      <AccordionContent>
                        ViPPET supports Intel CPUs, integrated and discrete GPUs,
                        and NPUs (Neural Processing Units) through OpenVINO and
                        DLStreamer.
                      </AccordionContent>
                    </AccordionItem>
                    <AccordionItem value="item-2">
                      <AccordionTrigger>
                        How are pipelines defined?
                      </AccordionTrigger>
                      <AccordionContent>
                        Pipelines are GStreamer-based definitions stored as YAML.
                        They chain together source, inference, and sink elements.
                      </AccordionContent>
                    </AccordionItem>
                    <AccordionItem value="item-3">
                      <AccordionTrigger>
                        What metrics are collected?
                      </AccordionTrigger>
                      <AccordionContent>
                        CPU/GPU/NPU utilization, power consumption, memory usage,
                        FPS, and latency metrics using Telegraf and custom collectors.
                      </AccordionContent>
                    </AccordionItem>
                  </Accordion>
                </CardContent>
              </Card>

              {/* Tooltip + Skeleton */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Tooltips</CardTitle>
                    <CardDescription>Hover for additional info</CardDescription>
                  </CardHeader>
                  <CardContent className="flex gap-3">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="outline">Hover me</Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>This shows helpful information</p>
                        </TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="outline">Warning</Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>Resource usage is high</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Skeleton</CardTitle>
                    <CardDescription>Loading state placeholders</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-20 w-full" />
                  </CardContent>
                </Card>
              </div>

              {/* Dialog + AlertDialog */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Dialog</CardTitle>
                    <CardDescription>Modal overlay windows</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Dialog>
                      <DialogTrigger asChild>
                        <Button variant="outline">Open Dialog</Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Pipeline Configuration</DialogTitle>
                          <DialogDescription>
                            Configure your inference pipeline settings.
                          </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-4">
                          <div className="space-y-2">
                            <Label>Pipeline Name</Label>
                            <Input placeholder="my-pipeline" />
                          </div>
                          <div className="space-y-2">
                            <Label>Description</Label>
                            <Textarea placeholder="Describe your pipeline..." />
                          </div>
                        </div>
                        <DialogFooter>
                          <Button variant="outline">Cancel</Button>
                          <Button>Save</Button>
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Alert Dialog</CardTitle>
                    <CardDescription>
                      Confirmation before destructive actions
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="destructive">Delete Pipeline</Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will permanently delete the pipeline and all
                            associated benchmark results.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel variant="outline" size="default">Cancel</AlertDialogCancel>
                          <AlertDialogAction variant="default" size="default">Delete</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </CardContent>
                </Card>
              </div>

              {/* Slider + Select */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Slider</CardTitle>
                    <CardDescription>
                      Configure number of parallel streams
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex justify-between text-sm">
                      <span>Streams</span>
                      <span className="font-medium">{sliderValue[0]}</span>
                    </div>
                    <Slider
                      value={sliderValue}
                      onValueChange={setSliderValue}
                      max={16}
                      min={1}
                      step={1}
                    />
                    <p className="text-xs text-muted-foreground">
                      Range: 1–16 concurrent streams
                    </p>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Select</CardTitle>
                    <CardDescription>
                      Choose inference device target
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <Select
                      value={selectedDevice}
                      onValueChange={setSelectedDevice}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select a device" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cpu">CPU (Intel Core)</SelectItem>
                        <SelectItem value="gpu">GPU (Intel Arc)</SelectItem>
                        <SelectItem value="npu">NPU (Intel AI Boost)</SelectItem>
                        <SelectItem value="auto">AUTO (Best available)</SelectItem>
                      </SelectContent>
                    </Select>
                    {selectedDevice && (
                      <p className="text-sm text-muted-foreground">
                        Selected: <Badge variant="outline">{selectedDevice.toUpperCase()}</Badge>
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Radio Group */}
              <Card>
                <CardHeader>
                  <CardTitle>Radio Group</CardTitle>
                  <CardDescription>
                    Single selection from multiple options
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <RadioGroup defaultValue="balanced">
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="performance" id="r1" />
                      <Label htmlFor="r1">Performance (max FPS)</Label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="balanced" id="r2" />
                      <Label htmlFor="r2">Balanced (FPS/power ratio)</Label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="efficiency" id="r3" />
                      <Label htmlFor="r3">Efficiency (min power)</Label>
                    </div>
                  </RadioGroup>
                </CardContent>
              </Card>

              {/* Progress */}
              <Card>
                <CardHeader>
                  <CardTitle>Progress</CardTitle>
                  <CardDescription>Shows completion status</CardDescription>
                </CardHeader>
                <CardContent>
                  <Progress value={65} max={100}>
                    <ProgressTrack>
                      <ProgressIndicator />
                    </ProgressTrack>
                  </Progress>
                </CardContent>
              </Card>
            </TabsContent>

            {/* ─── Form Tab ─── */}
            <TabsContent value="form" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Pipeline Configuration Form</CardTitle>
                  <CardDescription>
                    Complete form example with various input types
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="name">Pipeline Name</Label>
                      <Input
                        id="name"
                        placeholder="Enter pipeline name..."
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="device">Target Device</Label>
                      <Select>
                        <SelectTrigger>
                          <SelectValue placeholder="Select device" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="cpu">CPU</SelectItem>
                          <SelectItem value="gpu">GPU</SelectItem>
                          <SelectItem value="npu">NPU</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="feedback">Description</Label>
                    <Textarea
                      id="feedback"
                      placeholder="Describe the pipeline purpose..."
                      value={feedback}
                      onChange={(e) => setFeedback(e.target.value)}
                    />
                  </div>

                  <div className="space-y-3">
                    <Label>Options</Label>
                    <div className="flex items-center gap-2">
                      <Checkbox id="live-stream" />
                      <Label htmlFor="live-stream">Enable live stream output</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox id="recording" />
                      <Label htmlFor="recording">Record output video</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox id="benchmark" />
                      <Label htmlFor="benchmark">Run density benchmark after creation</Label>
                    </div>
                  </div>

                  {submitted && name && (
                    <div className="rounded-md bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 p-3">
                      <p className="text-sm text-green-700 dark:text-green-400">
                        Pipeline &ldquo;{name}&rdquo; created successfully!
                      </p>
                    </div>
                  )}
                </CardContent>
                <CardFooter className="flex gap-3">
                  <Button onClick={() => setSubmitted(true)}>
                    Create Pipeline
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setName("");
                      setFeedback("");
                      setSubmitted(false);
                    }}
                  >
                    Reset
                  </Button>
                </CardFooter>
              </Card>
            </TabsContent>

            {/* ─── Data Table Tab ─── */}
            <TabsContent value="data" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Benchmark Results</CardTitle>
                  <CardDescription>
                    Pipeline performance across hardware targets
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Pipeline</TableHead>
                        <TableHead>Device</TableHead>
                        <TableHead className="text-right">FPS</TableHead>
                        <TableHead className="text-right">Streams</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {benchmarkResults.map((result) => (
                        <TableRow key={result.pipeline} className="hover:bg-muted">
                          <TableCell className="font-medium">
                            {result.pipeline}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{result.device}</Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            {result.fps > 0 ? result.fps.toFixed(1) : "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            {result.streams > 0 ? result.streams : "—"}
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                result.status === "completed"
                                  ? "default"
                                  : result.status === "running"
                                    ? "secondary"
                                    : "destructive"
                              }
                            >
                              {result.status}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}

