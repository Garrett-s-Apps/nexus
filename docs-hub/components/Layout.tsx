import Link from 'next/link'
import Head from 'next/head'
import { useRouter } from 'next/router'

const navItems = [
  { href: '/', label: 'Home' },
  { href: '/overview', label: 'Overview' },
  { href: '/comparisons', label: 'vs Competitors' },
  { href: '/plugin', label: 'Plugin' },
  { href: '/sdk', label: 'SDK' },
  { href: '/use-cases', label: 'Use Cases' },
  { href: '/security', label: 'Security' },
]

export default function Layout({ children, title }: { children: React.ReactNode; title?: string }) {
  const router = useRouter()
  const pageTitle = title ? `${title} - NEXUS` : 'NEXUS Documentation'

  return (
    <div className="min-h-screen bg-gray-900">
      <Head>
        <title>{pageTitle}</title>
        <meta name="description" content="NEXUS enterprise multi-agent orchestration system documentation" />
      </Head>

      {/* Navigation */}
      <nav className="nav-container sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3">
          <div className="flex items-center justify-between">
            <Link href="/" className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              NEXUS
            </Link>
            <div className="flex space-x-1 overflow-x-auto">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-1.5 rounded text-sm whitespace-nowrap transition-colors ${
                    router.pathname === item.href
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-300 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </nav>

      {/* Content */}
      <main className="content-container py-8">
        <article className="prose prose-invert max-w-none">
          {children}
        </article>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-8 mt-16">
        <div className="max-w-7xl mx-auto px-4 text-center text-gray-500 text-sm">
          <p>NEXUS - Enterprise Multi-Agent Orchestration System</p>
          <p className="mt-1">Built by Garrett Eaglin</p>
        </div>
      </footer>
    </div>
  )
}