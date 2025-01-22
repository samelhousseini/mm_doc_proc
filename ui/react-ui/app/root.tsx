// app/root.tsx
import type { MetaFunction, LinksFunction } from "@remix-run/node"
import {
  Links,
  LiveReload,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration
} from "@remix-run/react"

import { ChakraProvider } from "@chakra-ui/react"
import { RecoilRoot } from "recoil"
import { ChainlitAPI, ChainlitContext } from "@chainlit/react-client"

import React from "react"

// Initialize chainlit client
const CHAINLIT_SERVER_URL = "http://localhost:8000" // or your server
const apiClient = new ChainlitAPI(CHAINLIT_SERVER_URL, "remix-app")

export const meta: MetaFunction = () => {
  return [
    { title: "Remix + Chainlit Demo" },
    { name: "description", content: "A Remix + Chakra + Chainlit integration." }
  ]
}
export default function Root() {
  return (
    <html lang="en">
      <head>
        <Meta />
        <Links />
      </head>
      <body>
        {/* Provide chainlit + recoil + chakra */}
        <ChainlitContext.Provider value={apiClient}>
          <RecoilRoot>
            <ChakraProvider>
              <Outlet /> 
              {/* <Outlet> is where child routes get rendered */}
            </ChakraProvider>
          </RecoilRoot>
        </ChainlitContext.Provider>

        <ScrollRestoration />
        <Scripts />
        <LiveReload />
      </body>
    </html>
  )
}
