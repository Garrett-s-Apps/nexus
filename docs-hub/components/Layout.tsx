import { useState } from 'react'
import Link from 'next/link'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { Stack, Row, Spread, Box, Divider } from './layoutkit'

const navItems = [
  { href: '/', label: 'Home' },
  { href: '/install', label: 'Install' },
  { href: '/overview', label: 'Overview' },
  { href: '/cli', label: 'CLI' },
  { href: '/plugin', label: 'Plugin' },
  { href: '/sdk', label: 'SDK' },
  { href: '/org-chart', label: 'Org Chart' },
  { href: '/comparisons', label: 'vs Competitors' },
  { href: '/use-cases', label: 'Use Cases' },
  { href: '/security', label: 'Security' },
]

export default function Layout({ children, title }: { children: React.ReactNode; title?: string }) {
  const router = useRouter()
  const pageTitle = title ? `${title} - NEXUS` : 'NEXUS Documentation'
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <Stack gap="none" className="min-h-screen bg-gray-900">
      <Head>
        <title>{pageTitle}</title>
        <meta name="description" content="NEXUS enterprise multi-agent orchestration system documentation" />
      </Head>

      {/* Top Bar */}
      <Box as="nav" className="nav-container sticky top-0 z-50 border-b border-gray-800">
        <Spread padding="md" className="max-w-7xl mx-auto">
          <Row gap="sm" className="items-center">
            {/* Hamburger for mobile */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden text-gray-300 hover:text-white p-1"
              aria-label="Toggle menu"
            >
              <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
                {mobileMenuOpen ? (
                  <path d="M6 6l12 12M6 18L18 6" />
                ) : (
                  <path d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
            {/* Sidebar toggle for desktop */}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="hidden md:block text-gray-400 hover:text-white p-1 transition-colors"
              aria-label="Toggle sidebar"
              title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
            >
              <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                {sidebarOpen ? (
                  <path d="M3 3h14M3 8h10M3 13h14M3 18h10" />
                ) : (
                  <path d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
            <Link href="/" className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              NEXUS
            </Link>
          </Row>
          <Row gap="xs" className="hidden md:flex">
            <a href="https://www.npmjs.com/package/buildwithnexus" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white text-sm transition-colors">
              npm
            </a>
            <a href="https://github.com/Garrett-s-Apps/buildwithnexus" target="_blank" rel="noopener noreferrer" className="text-gray-400 hover:text-white text-sm transition-colors">
              GitHub
            </a>
          </Row>
        </Spread>
      </Box>

      {/* Mobile menu overlay */}
      {mobileMenuOpen && (
        <Box className="md:hidden fixed inset-0 z-40 bg-gray-900/95 pt-16">
          <Stack gap="xs" padding="lg">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`px-4 py-3 rounded-lg text-lg transition-colors ${
                  router.pathname === item.href
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-300 hover:text-white hover:bg-gray-800'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </Stack>
        </Box>
      )}

      {/* Main layout with sidebar */}
      <Row gap="none" className="flex-1">
        {/* Sidebar - collapsible on desktop, hidden on mobile */}
        <Box
          as="aside"
          className={`hidden md:block border-r border-gray-800 bg-gray-900/50 transition-all duration-200 ${
            sidebarOpen ? 'w-56' : 'w-0 overflow-hidden'
          }`}
        >
          <Stack gap="xs" padding={sidebarOpen ? 'md' : 'none'} className="sticky top-14">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-3 py-2 rounded-lg text-sm transition-colors ${
                  router.pathname === item.href
                    ? 'bg-blue-600/20 text-blue-400 border-l-2 border-blue-400'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </Stack>
        </Box>

        {/* Content */}
        <Box as="main" padding="lg" className="content-container flex-1 min-w-0">
          <article className="prose prose-invert max-w-none">
            {children}
          </article>
        </Box>
      </Row>

      {/* Footer */}
      <Divider color="border-gray-800" />
      <Box as="footer" padding="lg" className="mt-16">
        <Stack gap="xs" align="center" className="max-w-7xl mx-auto text-gray-500 text-sm">
          <p>NEXUS - Enterprise Multi-Agent Orchestration System</p>
          <p>Built by Garrett Eaglin</p>
        </Stack>
      </Box>
    </Stack>
  )
}
