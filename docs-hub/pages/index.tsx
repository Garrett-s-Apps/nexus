import Head from 'next/head'
import Link from 'next/link'
import { Stack, Row, Grid, Center, Box } from '../components/layoutkit'

export default function Home() {
  return (
    <Stack gap="none" fill className="bg-gradient-to-br from-gray-900 via-blue-900 to-indigo-900">
      <Head>
        <title>NEXUS - Enterprise Multi-Agent Orchestration System</title>
        <meta name="description" content="Autonomous software engineering organization with 56 agents. Tell it what to build. It figures out the rest." />
        <link rel="icon" href="/favicon.ico" />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          "name": "NEXUS",
          "applicationCategory": "DeveloperApplication",
          "operatingSystem": "macOS, Linux",
          "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
          "description": "Enterprise multi-agent orchestration system with 56 autonomous agents, interactive CLI, and real-time agent streaming.",
          "url": "https://buildwithnexus.dev",
          "downloadUrl": "https://www.npmjs.com/package/buildwithnexus"
        }) }} />
      </Head>

      <Box padding="xl" className="max-w-[1200px] mx-auto w-full">
        {/* Hero Section */}
        <Center className="mb-16 pt-8">
          <Stack gap="lg" align="center" className="text-center">
            <h1 className="text-6xl font-bold text-white">
              <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                NEXUS
              </span>
            </h1>
            <p className="text-xl text-gray-300">Enterprise Multi-Agent Orchestration System</p>
            <p className="text-3xl text-white max-w-4xl">
              A 56-agent autonomous software engineering organization. Tell it what to build. It figures out the rest.
            </p>
            <Row gap="md" justify="center">
              <Link href="/install" className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-semibold transition-colors">
                Install Now
              </Link>
              <Link href="/overview" className="border border-gray-400 hover:border-white text-gray-300 hover:text-white px-8 py-3 rounded-lg font-semibold transition-colors">
                Get Started
              </Link>
              <Link href="/comparisons" className="border border-gray-400 hover:border-white text-gray-300 hover:text-white px-8 py-3 rounded-lg font-semibold transition-colors">
                vs Competitors
              </Link>
            </Row>
            <code className="text-gray-400 text-lg bg-gray-800 px-4 py-2 rounded-lg">buildwithnexus&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; # launch interactive shell</code>
          </Stack>
        </Center>

        {/* Key Features */}
        <Grid cols={3} gap="lg" className="mb-16" responsive minChildWidth="280px">
          <Stack gap="md" padding="lg" className="bg-gray-800 rounded-lg">
            <h3 className="text-xl font-bold text-white">Autonomous Organization</h3>
            <p className="text-gray-300">
              You are the CEO. NEXUS provides a Chief of Staff, VPs, managers, and 56 specialist agents that plan, execute, and learn autonomously on your behalf.
            </p>
          </Stack>
          <Stack gap="md" padding="lg" className="bg-gray-800 rounded-lg">
            <h3 className="text-xl font-bold text-white">Self-Learning System</h3>
            <p className="text-gray-300">
              ML models learn from every outcome, predict costs, route tasks to best agents, and remember past work via RAG knowledge base.
            </p>
          </Stack>
          <Stack gap="md" padding="lg" className="bg-gray-800 rounded-lg">
            <h3 className="text-xl font-bold text-white">Enterprise Security</h3>
            <p className="text-gray-300">
              Encrypted databases, Docker sandboxing, JWT authentication, and comprehensive audit trails.
            </p>
          </Stack>
        </Grid>

        {/* Navigation Grid */}
        <Grid cols={3} gap="md" className="max-w-6xl mx-auto" responsive minChildWidth="280px">
          <Link href="/install" className="group bg-blue-900 hover:bg-blue-800 rounded-lg transition-colors border border-blue-700">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">Install</h3>
              <p className="text-gray-300 text-sm">npm package, quick start, commands, and DLP security</p>
            </Stack>
          </Link>

          <Link href="/cli" className="group bg-indigo-900 hover:bg-indigo-800 rounded-lg transition-colors border border-indigo-700">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-indigo-400">Interactive CLI</h3>
              <p className="text-gray-300 text-sm">Claude Code-like terminal with real-time agent streaming</p>
            </Stack>
          </Link>

          <Link href="/overview" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">System Overview</h3>
              <p className="text-gray-300 text-sm">Architecture, workflow, and how NEXUS operates</p>
            </Stack>
          </Link>

          <Link href="/comparisons" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">vs Competitors</h3>
              <p className="text-gray-300 text-sm">How NEXUS compares to OpenClaw, Devin, Codex, Claude Code</p>
            </Stack>
          </Link>

          <Link href="/plugin" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">Claude Code Plugin</h3>
              <p className="text-gray-300 text-sm">Skills, commands, and integration guide</p>
            </Stack>
          </Link>

          <Link href="/sdk" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">Python SDK</h3>
              <p className="text-gray-300 text-sm">Multi-agent orchestration SDK with swappable providers</p>
            </Stack>
          </Link>

          <Link href="/use-cases" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">Use Cases</h3>
              <p className="text-gray-300 text-sm">Walkthroughs, tutorials, and real-world examples</p>
            </Stack>
          </Link>

          <Link href="/security" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
            <Stack gap="sm" padding="lg">
              <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">Security & Compliance</h3>
              <p className="text-gray-300 text-sm">Encryption, sandboxing, and enterprise controls</p>
            </Stack>
          </Link>
        </Grid>

        {/* Ecosystem */}
        <Stack gap="lg" className="mt-16 mb-16">
          <Center>
            <h2 className="text-3xl font-bold text-white">Ecosystem</h2>
          </Center>
          <Grid cols={2} gap="md" responsive minChildWidth="280px">
            <a href="https://layoutkit.dev" target="_blank" rel="noopener noreferrer" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors border border-gray-700 hover:border-blue-500">
              <Stack gap="sm" padding="lg">
                <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">LayoutKit</h3>
                <p className="text-gray-300 text-sm">10 semantic React components that compile to Tailwind CSS. The layout system powering this site.</p>
                <code className="text-xs text-gray-400 bg-gray-900 px-2 py-1 rounded w-fit">npm install layoutkit-css</code>
              </Stack>
            </a>
            <a href="https://www.npmjs.com/package/buildwithnexus" target="_blank" rel="noopener noreferrer" className="group bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors border border-gray-700 hover:border-blue-500">
              <Stack gap="sm" padding="lg">
                <h3 className="text-lg font-semibold text-white group-hover:text-blue-400">NEXUS CLI</h3>
                <p className="text-gray-300 text-sm">Autonomous AI runtime with triple-nested VM isolation. One command to bootstrap.</p>
                <code className="text-xs text-gray-400 bg-gray-900 px-2 py-1 rounded w-fit">npx buildwithnexus init</code>
              </Stack>
            </a>
          </Grid>
        </Stack>

        {/* Stats Section */}
        <Center className="mt-16">
          <Stack gap="lg" align="center">
            <h2 className="text-3xl font-bold text-white">Built for Scale</h2>
            <Grid cols={4} gap="lg" className="max-w-4xl" responsive minChildWidth="150px">
              <Center>
                <Stack gap="xs" align="center">
                  <div className="text-4xl font-bold text-blue-400">56</div>
                  <div className="text-gray-300">Active Agents</div>
                </Stack>
              </Center>
              <Center>
                <Stack gap="xs" align="center">
                  <div className="text-4xl font-bold text-purple-400">7</div>
                  <div className="text-gray-300">Encrypted Databases</div>
                </Stack>
              </Center>
              <Center>
                <Stack gap="xs" align="center">
                  <div className="text-4xl font-bold text-green-400">27</div>
                  <div className="text-gray-300">Orchestration Nodes</div>
                </Stack>
              </Center>
              <Center>
                <Stack gap="xs" align="center">
                  <div className="text-4xl font-bold text-orange-400">100%</div>
                  <div className="text-gray-300">Encrypted at Rest</div>
                </Stack>
              </Center>
            </Grid>
          </Stack>
        </Center>
      </Box>
    </Stack>
  )
}
