import { useState } from "react";
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Input,
  Label,
  Badge,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Separator,
  Checkbox,
  Progress,
  ProgressTrack,
  ProgressIndicator,
} from "@vippet/ui";

export function App() {
  const [darkMode, setDarkMode] = useState(false);
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);

  return (
    <div className={darkMode ? "dark" : ""}>
      <div className="min-h-screen bg-background text-foreground p-8">
        <div className="mx-auto max-w-3xl space-y-8">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">@vippet/ui Example</h1>
              <p className="text-muted-foreground mt-1">
                A simple app demonstrating the component library
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

          {/* Tabs demo */}
          <Tabs defaultValue="components">
            <TabsList>
              <TabsTrigger value="components">Components</TabsTrigger>
              <TabsTrigger value="form">Form</TabsTrigger>
            </TabsList>

            <TabsContent value="components" className="space-y-6 mt-4">
              {/* Buttons */}
              <Card>
                <CardHeader>
                  <CardTitle>Buttons</CardTitle>
                  <CardDescription>
                    Various button variants available in the library
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-3">
                  <Button>Default</Button>
                  <Button variant="secondary">Secondary</Button>
                  <Button variant="outline">Outline</Button>
                  <Button variant="ghost">Ghost</Button>
                  <Button variant="destructive">Destructive</Button>
                  <Button variant="link">Link</Button>
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

            <TabsContent value="form" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Simple Form</CardTitle>
                  <CardDescription>
                    Input, checkbox, and button working together
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Name</Label>
                    <Input
                      id="name"
                      placeholder="Enter your name..."
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox id="terms" />
                    <Label htmlFor="terms">I agree to the terms</Label>
                  </div>
                  {submitted && name && (
                    <p className="text-sm text-green-600">
                      Hello, {name}! Form submitted successfully.
                    </p>
                  )}
                </CardContent>
                <CardFooter>
                  <Button onClick={() => setSubmitted(true)}>Submit</Button>
                </CardFooter>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
