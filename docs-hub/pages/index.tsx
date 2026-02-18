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
              <Link href="/overview" className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-semibold transition-colors">
                Get Started
              </Link>
              <Link href="/comparisons" className="border border-gray-400 hover:border-white text-gray-300 hover:text-white px-8 py-3 rounded-lg font-semibold transition-colors">
                vs Competitors
              </Link>
            </Row>
          </Stack>
        </Center>

        {/* Key Features */}
        <Grid cols={3} gap="lg" className="mb-16" responsive minChildWidth="280px">
          <Stack gap="md" padding="lg" className="bg-gray-800 rounded-lg">
            <h3 className="text-xl font-bold text-white">Autonomous Organization</h3>
            <p className="text-gray-300">
              CEO, VPs, managers, senior engineers, specialists — a complete org chart with 56 agents that plan, execute, and learn autonomously.
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
              SOC 2 Type II controls, encrypted databases, Docker sandboxing, JWT authentication, and comprehensive audit trails.
            </p>
          </Stack>
        </Grid>

        {/* Navigation Grid */}
        <Grid cols={3} gap="md" className="max-w-6xl mx-auto" responsive minChildWidth="280px">
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
              <p className="text-gray-300 text-sm">SOC 2, encryption, sandboxing, and enterprise controls</p>
            </Stack>
          </Link>
        </Grid>

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
                  <div className="text-4xl font-bold text-orange-400">SOC 2</div>
                  <div className="text-gray-300">Type II Compliance</div>
                </Stack>
              </Center>
            </Grid>
          </Stack>
        </Center>
      </Box>
    </Stack>
  )
}
