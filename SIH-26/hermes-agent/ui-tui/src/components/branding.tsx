import { Box, Text, useStdout } from '@hermes/ink'
import { useEffect, useState } from 'react'
import unicodeSpinners from 'unicode-animations'

import { artWidth, caduceus, CADUCEUS_WIDTH, logo, LOGO_WIDTH } from '../banner.js'
import { mix } from '../lib/color.js'
import { flat } from '../lib/text.js'
import type { Theme } from '../theme.js'
import type { PanelSection, SessionInfo } from '../types.js'

import { Accordion } from './accordion.js'
import { ShimmerRows } from './loaders.js'
import { WidgetGrid } from './widgetGrid.js'

const LOADER_TICK_MS = 120

function InlineLoader({ label, t }: { label: string; t: Theme }) {
  const [tick, setTick] = useState(0)
  const spinner = unicodeSpinners.braille
  const frame = spinner.frames[tick % spinner.frames.length] ?? '⠋'

  useEffect(() => {
    const id = setInterval(() => setTick(n => n + 1), Math.max(LOADER_TICK_MS, spinner.interval))

    return () => clearInterval(id)
  }, [spinner.interval])

  return (
    <Text color={t.color.muted} wrap="truncate">
      <Text color={t.color.accent}>{frame}</Text> {label}
    </Text>
  )
}

export function ArtLines({ lines }: { lines: [string, string][] }) {
  // No `opaque`: the banner is top-level content with nothing behind it, so
  // it never needs the opaque space-fill (that's for absolute overlays). On a
  // transparent terminal (terminal.background #00000000) the fill's "default
  // background" spaces composite to black bars instead of the intended
  // see-through — the reported ugly banner. Glyphs paint fine on their own.
  return (
    <Box flexDirection="column" height={lines.length} width={artWidth(lines)}>
      {lines.map(([c, text], i) => (
        <Text color={c} key={i} wrap="truncate-end">
          {text}
        </Text>
      ))}
    </Box>
  )
}

const HIDE_BELOW = 34

export function Banner({ maxWidth, t }: { maxWidth?: number; t: Theme }) {
  const term = useStdout().stdout?.columns ?? 80
  const cols = Math.max(1, Math.min(term, maxWidth ?? term))

  if (cols < HIDE_BELOW) {
    return null
  }

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text bold color={t.color.primary}>INDRA</Text>
      <Text bold color={t.color.text}>SOVEREIGN INTELLIGENCE WORKBENCH</Text>
      <Text color={t.color.muted}>Intelligence Within Your Perimeter.</Text>
    </Box>
  )
}

// ── Skeleton ─────────────────────────────────────────────────────────
//
// Lazy sections render shimmer rows shaped like the real content (label
// block + value run) instead of a blank gap that pops when data lands.
// Row widths mirror the typical toolsets listing.
const SKELETON_ROWS: readonly (readonly [number, number])[] = [
  [7, 30],
  [7, 9],
  [14, 12],
  [12, 12],
  [7, 7],
  [10, 13]
]

export function SessionPanel({ info, maxWidth, sid, t }: SessionPanelProps) {
  const toolsTotal = flat(info.tools).length
  const skillsTotal = flat(info.skills).length

  return (
    <Box borderColor={t.color.border} borderStyle="single" flexDirection="column" marginBottom={1} paddingX={2} paddingY={1}>
      <Box flexDirection="column" marginBottom={1}>
        <Text bold color={t.color.accent}>01 / RUNTIME</Text>
        <Text>
          <Text color={t.color.muted}>{'LOCAL MODEL       '}</Text>
          <Text color={t.color.text}>{info.model.split('/').pop()}</Text>
        </Text>
        <Text>
          <Text color={t.color.muted}>{'EXECUTION         '}</Text>
          <Text color={t.color.text}>DOCKER</Text>
        </Text>
        <Text>
          <Text color={t.color.muted}>{'NETWORK           '}</Text>
          <Text color={t.color.text}>CONTROLLED</Text>
        </Text>
        {sid && (
          <Text>
            <Text color={t.color.muted}>{'SESSION           '}</Text>
            <Text color={t.color.text}>{sid}</Text>
          </Text>
        )}
      </Box>

      <Box flexDirection="column">
        <Text bold color={t.color.accent}>02 / CAPABILITIES</Text>
        <Text>
          <Text color={t.color.text}>{toolsTotal}</Text>
          <Text color={t.color.muted}>{' TOOLS       '}</Text>
          <Text color={t.color.text}>{skillsTotal}</Text>
          <Text color={t.color.muted}>{' SKILLS'}</Text>
        </Text>
        <Text>
          <Text color={t.color.muted}>{'TYPE '}</Text>
          <Text color={t.color.text}>{'/HELP'}</Text>
          <Text color={t.color.muted}>{'        FOR COMMANDS'}</Text>
        </Text>
      </Box>
    </Box>
  )
}

export function Panel({ sections, t, title }: PanelProps) {
  return (
    <Box borderColor={t.color.border} borderStyle="single" flexDirection="column" paddingX={2} paddingY={1}>
      <Box justifyContent="center" marginBottom={1}>
        <Text bold color={t.color.primary}>
          {title}
        </Text>
      </Box>

      {sections.map((sec, si) => (
        <Box flexDirection="column" key={si} marginTop={si > 0 ? 1 : 0}>
          {sec.title && (
            <Text bold color={t.color.accent}>
              {sec.title}
            </Text>
          )}

          {sec.rows?.map(([k, v], ri) => (
            <Text key={ri} wrap="truncate">
              <Text color={t.color.muted}>{k.padEnd(20)}</Text>
              <Text color={t.color.text}>{v}</Text>
            </Text>
          ))}

          {sec.items?.map((item, ii) => (
            <Text color={t.color.text} key={ii} wrap="truncate">
              {item}
            </Text>
          ))}

          {sec.text && <Text color={t.color.muted}>{sec.text}</Text>}
        </Box>
      ))}
    </Box>
  )
}

interface PanelProps {
  sections: PanelSection[]
  t: Theme
  title: string
}

interface SessionPanelProps {
  info: SessionInfo
  maxWidth?: number
  sid?: string | null
  t: Theme
}
