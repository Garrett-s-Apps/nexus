import '../styles/globals.css'
import type { AppProps } from 'next/app'
import Head from 'next/head'
import { useRouter } from 'next/router'
import Layout from '../components/Layout'

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const isHome = router.pathname === '/'

  const sharedMeta = (
    <>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <link rel="icon" href="/favicon.ico" />
      <meta name="keywords" content="NEXUS, buildwithnexus, multi-agent orchestration, autonomous AI, interactive CLI, real-time agent streaming, Claude Code plugin, Python SDK, enterprise security, Docker isolation, npm install buildwithnexus" />
      <meta property="og:site_name" content="Build With NEXUS" />
      <meta property="og:type" content="website" />
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content="NEXUS - Enterprise Multi-Agent Orchestration" />
      <meta name="twitter:description" content="56-agent autonomous engineering org. Interactive CLI with real-time streaming. npm install -g buildwithnexus." />
    </>
  )

  if (isHome) {
    return (
      <>
        <Head>
          {sharedMeta}
        </Head>
        <Component {...pageProps} />
      </>
    )
  }

  return (
    <>
      <Head>
        {sharedMeta}
      </Head>
      <Layout>
        <Component {...pageProps} />
      </Layout>
    </>
  )
}