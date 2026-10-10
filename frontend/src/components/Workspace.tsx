"use client";

import { AnimatePresence, motion } from "motion/react";
import { AppDock } from "./AppDock";
import { Backdrop } from "./Backdrop";
import { CompareSheet } from "./CompareSheet";
import { ChatThread } from "./ChatThread";
import { Hero } from "./Hero";
import { Tour } from "./Tour";
import { Nav } from "./Nav";
import { ProfileDrawer } from "./ProfileDrawer";
import { PromptBar } from "./PromptBar";
import { AccessScreen, FatalScreen, LoadingScreen, Toasts } from "./StatusScreens";
import { WhySheet } from "./WhySheet";
import { useWorkspace, WorkspaceProvider } from "./WorkspaceProvider";

function Shell() {
  const { ready, locked, fatal, messages } = useWorkspace();
  const chatting = messages.length > 0;

  return (
    <>
      <Backdrop />
      {!ready ? (
        <LoadingScreen />
      ) : locked ? (
        <AccessScreen />
      ) : fatal ? (
        <FatalScreen message={fatal} />
      ) : (
        <>
          <Nav />
          <AppDock current="chat" />
          <main id="main" className="relative min-h-dvh">
            <AnimatePresence mode="wait" initial={false}>
              {chatting ? (
                <motion.div key="chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }}>
                  <ChatThread />
                </motion.div>
              ) : (
                <motion.div key="hero" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -24, filter: "blur(10px)" }} transition={{ duration: 0.4 }}>
                  <Hero />
                </motion.div>
              )}
            </AnimatePresence>
          </main>

          {chatting && (
            <div className="fixed inset-x-0 bottom-0 z-30 px-3 pb-4 sm:px-6 sm:pb-6">
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-black via-black/70 to-transparent" aria-hidden />
              <div className="relative mx-auto max-w-3xl">
                <PromptBar autoFocus />
              </div>
            </div>
          )}
          <ProfileDrawer />
          <CompareSheet />
          <WhySheet />
          <Toasts />
          <Tour />
        </>
      )}
    </>
  );
}

export function Workspace() {
  return (
    <WorkspaceProvider>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[80] focus:rounded-full focus:bg-white focus:px-4 focus:py-2 focus:text-black">
        Skip to content
      </a>
      <Shell />
    </WorkspaceProvider>
  );
}
