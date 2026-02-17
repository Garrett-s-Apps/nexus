import Head from 'next/head'
import Link from 'next/link'

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-indigo-900">
      <Head>
        <title>NEXUS - Enterprise Multi-Agent Orchestration System</title>
        <meta name="description" content="Autonomous software engineering organization with 56 agents. Tell it what to build. It figures out the rest." />
        <link rel="icon" href="/favicon.ico" />
      </Head>

      <div className="container mx-auto px-4 py-16">
        {/* Hero Section */}
        <div className="text-center mb-16">
          <h1 className="text-6xl font-bold text-white mb-6">
            <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              NEXUS
            </span>
          </h1>
          <p className="text-xl text-gray-300 mb-4">Enterprise Multi-Agent Orchestration System</p>
          <p className="text-3xl text-white mb-8 max-w-4xl mx-auto">
            A 56-agent autonomous software engineering organization. Tell it what to build. It figures out the rest.
          </p>
          <div className="flex justify-center space-x-4">
            <Link href="/overview" className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-lg font-semibold transition-colors">
              Get Started
            </Link>
            <Link href="/comparisons" className="border border-gray-400 hover:border-white text-gray-300 hover:text-white px-8 py-3 rounded-lg font-semibold transition-colors">
              vs Competitors
            </Link>
          </div>
        </div>

        {/* Key Features */}
        <div className="grid md:grid-cols-3 gap-8 mb-16">
          <div className="bg-gray-800 p-8 rounded-lg">
            <h3 className="text-xl font-bold text-white mb-4">🤖 Autonomous Organization</h3>
            <p className="text-gray-300">
              CEO, VPs, managers, senior engineers, specialists — a complete org chart with 56 agents that plan, execute, and learn autonomously.
            </p>
          </div>
          <div className="bg-gray-800 p-8 rounded-lg">
            <h3 className="text-xl font-bold text-white mb-4">🧠 Self-Learning System</h3>
            <p className="text-gray-300">
              ML models learn from every outcome, predict costs, route tasks to best agents, and remember past work via RAG knowledge base.
            </p>
          </div>
          <div className="bg-gray-800 p-8 rounded-lg">
            <h3 className="text-xl font-bold text-white mb-4">🔒 Enterprise Security</h3>
            <p className="text-gray-300">
              SOC 2 Type II controls, encrypted databases, Docker sandboxing, JWT authentication, and comprehensive audit trails.
            </p>
          </div>
        </div>

        {/* Navigation Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-6xl mx-auto">
          <Link href="/overview" className="group bg-gray-800 hover:bg-gray-700 p-6 rounded-lg transition-colors">
            <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-blue-400">📚 System Overview</h3>
            <p className="text-gray-300 text-sm">Architecture, workflow, and how NEXUS operates</p>
          </Link>

          <Link href="/comparisons" className="group bg-gray-800 hover:bg-gray-700 p-6 rounded-lg transition-colors">
            <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-blue-400">⚔️ vs Competitors</h3>
            <p className="text-gray-300 text-sm">How NEXUS compares to OpenClaw, Devin, Codex, Claude Code</p>
          </Link>

          <Link href="/plugin" className="group bg-gray-800 hover:bg-gray-700 p-6 rounded-lg transition-colors">
            <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-blue-400">🔌 Claude Code Plugin</h3>
            <p className="text-gray-300 text-sm">Skills, commands, and integration guide</p>
          </Link>

          <Link href="/sdk" className="group bg-gray-800 hover:bg-gray-700 p-6 rounded-lg transition-colors">
            <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-blue-400">🛠️ Python SDK</h3>
            <p className="text-gray-300 text-sm">Multi-agent orchestration SDK with swappable providers</p>
          </Link>

          <Link href="/use-cases" className="group bg-gray-800 hover:bg-gray-700 p-6 rounded-lg transition-colors">
            <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-blue-400">💡 Use Cases</h3>
            <p className="text-gray-300 text-sm">Walkthroughs, tutorials, and real-world examples</p>
          </Link>

          <Link href="/security" className="group bg-gray-800 hover:bg-gray-700 p-6 rounded-lg transition-colors">
            <h3 className="text-lg font-semibold text-white mb-2 group-hover:text-blue-400">🛡️ Security & Compliance</h3>
            <p className="text-gray-300 text-sm">SOC 2, encryption, sandboxing, and enterprise controls</p>
          </Link>
        </div>

        {/* Stats Section */}
        <div className="mt-16 text-center">
          <h2 className="text-3xl font-bold text-white mb-8">Built for Scale</h2>
          <div className="grid md:grid-cols-4 gap-8 max-w-4xl mx-auto">
            <div>
              <div className="text-4xl font-bold text-blue-400 mb-2">56</div>
              <div className="text-gray-300">Active Agents</div>
            </div>
            <div>
              <div className="text-4xl font-bold text-purple-400 mb-2">7</div>
              <div className="text-gray-300">Encrypted Databases</div>
            </div>
            <div>
              <div className="text-4xl font-bold text-green-400 mb-2">27</div>
              <div className="text-gray-300">Orchestration Nodes</div>
            </div>
            <div>
              <div className="text-4xl font-bold text-orange-400 mb-2">SOC 2</div>
              <div className="text-gray-300">Type II Compliance</div>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        .container {
          max-width: 1200px;
        }
      `}</style>
    </div>
  )
}