import Link from 'next/link'
import Head from 'next/head'
import { useRouter } from 'next/router'
import { Stack, Row, Spread, Box, Divider } from './layoutkit'

const navItems = [
  { href: '/', label: 'Home' },
  { href: '/install', label: 'Install' },
  { href: '/overview', label: 'Overview' },
  { href: '/comparisons', label: 'vs Competitors' },
  { href: '/plugin', label: 'Plugin' },
  { href: '/sdk', label: 'SDK' },
  { href: '/cli', label: 'CLI' },
  { href: '/use-cases', label: 'Use Cases' },
  { href: '/security', label: 'Security' },
]

export default function Layout({ children, title }: { children: React.ReactNode; title?: string }) {
  const router = useRouter()
  const pageTitle = title ? `${title} - NEXUS` : 'NEXUS Documentation'

  return (
    <Stack gap="none" className="min-h-screen bg-gray-900">
      <Head>
        <title>{pageTitle}</title>
        <meta name="description" content="NEXUS enterprise multi-agent orchestration system documentation" />
      </Head>

      {/* Navigation */}
      <Box as="nav" className="nav-container sticky top-0 z-50">
        <Spread padding="md" className="max-w-7xl mx-auto">
          <Link href="/" className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
            NEXUS
          </Link>
          <Row gap="xs" className="overflow-x-auto">
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
          </Row>
        </Spread>
      </Box>

      {/* Content */}
      <Box as="main" padding="lg" className="content-container flex-1">
        <article className="prose prose-invert max-w-none">
          {children}
        </article>
      </Box>

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
