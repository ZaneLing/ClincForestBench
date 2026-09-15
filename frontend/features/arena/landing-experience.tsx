'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  BrainCircuit,
  Database,
  GitBranch,
  ShieldCheck,
  Stethoscope,
  Trees,
  UserRound,
  UsersRound,
} from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';

export function LandingExperience() {
  const reduceMotion = useReducedMotion();
  const [scene, setScene] = useState(0);
  const sceneLabels = ['病例生长', '医生共建', '路径成林'];

  useEffect(() => {
    if (reduceMotion) return;
    const timer = window.setInterval(
      () => setScene((current) => (current + 1) % sceneLabels.length),
      5_200,
    );
    return () => window.clearInterval(timer);
  }, [reduceMotion, sceneLabels.length]);

  return (
    <motion.section
      animate={{ opacity: 1 }}
      className="bench-landing"
      exit={{ opacity: 0, scale: 0.985 }}
      initial={{ opacity: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="clinical-cross cross-one">+</div>
      <div className="clinical-cross cross-two">+</div>
      <div className="landing-aura aura-one" />
      <div className="landing-aura aura-two" />

      <div className="landing-content">
        <motion.div
          animate={{ opacity: 1, y: 0 }}
          className="landing-copy"
          initial={{ opacity: 0, y: 18 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        >
          <p className="landing-eyebrow">
            <ShieldCheck /> Evidence-locked · Oracle-protected
          </p>
          <h1>
            <span>Clinc</span>ForestBench
          </h1>
          <p className="landing-lead">
            从一次问询、一条临床记录、一次 FHIR 操作开始。医生逐步暴露信息、提交判断，
            独立的决策路径由此生长、分叉，并汇聚成可比较的临床决策森林。
          </p>
          <div className="landing-cta-row">
            <Button render={<Link href="/arena" />} size="lg">
              <Stethoscope /> Enter the Arena
              <ArrowRight />
            </Button>
            <Link href="/research">
              Inspect source → tree <GitBranch />
            </Link>
          </div>
        </motion.div>

        <motion.div
          animate={{ opacity: 1, y: 0 }}
          className="diagnostic-orbit"
          initial={{ opacity: 0, y: 24 }}
          transition={{ delay: 0.15, duration: 0.7 }}
        >
          <div className="orbit-status">
            <Activity /> {sceneLabels[scene]}
            <span>
              {scene === 0
                ? 'S0 → S1 → S2'
                : scene === 1
                  ? 'DR 01 → DR N'
                  : 'PATHS → FOREST'}
            </span>
          </div>
          <AnimatePresence mode="wait">
            <motion.div
              animate={{ opacity: 1, scale: 1 }}
              className="orbit-scene"
              exit={{ opacity: 0, scale: 0.97 }}
              initial={{ opacity: 0, scale: 1.02 }}
              key={scene}
              transition={{ duration: 0.55 }}
            >
              {scene === 0 && (
                <PatientTraceScene reduceMotion={Boolean(reduceMotion)} />
              )}
              {scene === 1 && (
                <DoctorGrowthScene reduceMotion={Boolean(reduceMotion)} />
              )}
              {scene === 2 && (
                <ForestFormationScene reduceMotion={Boolean(reduceMotion)} />
              )}
            </motion.div>
          </AnimatePresence>
          <div className="orbit-scene-switcher" aria-label="开场动画场景">
            {sceneLabels.map((label, index) => (
              <button
                aria-label={label}
                className={scene === index ? 'is-active' : undefined}
                key={label}
                onClick={() => setScene(index)}
                type="button"
              />
            ))}
          </div>
        </motion.div>

        <div className="landing-stats">
          <LandingStat value="170" label="Versioned cases" />
          <LandingStat value="8" label="Dataset tracks" />
          <LandingStat value="130+40" label="Classic · Temporal" />
          <LandingStat value="Sₙ" label="Belief checkpoints" />
        </div>
      </div>
    </motion.section>
  );
}

function PatientTraceScene({ reduceMotion }: { reduceMotion: boolean }) {
  const pathTransition = reduceMotion
    ? { duration: 0 }
    : { duration: 2.2, repeat: Infinity, repeatDelay: 0.7 };
  return (
    <>
      <svg
        aria-hidden="true"
        className="orbit-lines"
        preserveAspectRatio="none"
        viewBox="0 0 920 300"
      >
        <defs>
          <linearGradient id="clinical-path" x1="0" x2="1">
            <stop offset="0" stopColor="#22d3ee" />
            <stop offset="0.55" stopColor="#818cf8" />
            <stop offset="1" stopColor="#34d399" />
          </linearGradient>
          <filter id="clinical-glow">
            <feGaussianBlur result="blur" stdDeviation="4" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <motion.path
          animate={{ pathLength: 1, pathOffset: [0, 0.08, 0] }}
          d="M90 150 C190 150 200 72 315 72 S420 150 500 150"
          fill="none"
          filter="url(#clinical-glow)"
          initial={{ pathLength: 0 }}
          stroke="url(#clinical-path)"
          strokeLinecap="round"
          strokeWidth="3"
          transition={pathTransition}
        />
        <motion.path
          animate={{ pathLength: 1 }}
          d="M500 150 C600 150 625 70 730 70 L835 70"
          fill="none"
          initial={{ pathLength: 0 }}
          stroke="url(#clinical-path)"
          strokeLinecap="round"
          strokeWidth="3"
          transition={{ ...pathTransition, delay: 0.45 }}
        />
        <motion.path
          animate={{ pathLength: 1 }}
          d="M500 150 C600 150 625 230 730 230 L835 230"
          fill="none"
          initial={{ pathLength: 0 }}
          stroke="url(#clinical-path)"
          strokeLinecap="round"
          strokeWidth="3"
          transition={{ ...pathTransition, delay: 0.75 }}
        />
      </svg>
      <OrbitNode className="orbit-patient" delay={0.15} icon={<UserRound />}>
        <span>Patient</span>
        <b>Initial state</b>
      </OrbitNode>
      <OrbitNode className="orbit-evidence" delay={0.45} icon={<Database />}>
        <span>Evidence</span>
        <b>Ask & observe</b>
      </OrbitNode>
      <OrbitNode className="orbit-belief" delay={0.75} icon={<BrainCircuit />}>
        <span>Belief</span>
        <b>Commit at Sₙ</b>
      </OrbitNode>
      <OrbitNode className="orbit-correct" delay={1.05} icon={<BadgeCheck />}>
        <span>Converged path</span>
        <b>Ground truth</b>
      </OrbitNode>
      <OrbitNode className="orbit-branch" delay={1.2} icon={<GitBranch />}>
        <span>Alternative path</span>
        <b>Reasoning branch</b>
      </OrbitNode>
      <motion.div
        animate={reduceMotion ? {} : { opacity: [0.3, 1, 0.3] }}
        className="orbit-scanner"
        transition={{ duration: 2.5, repeat: Infinity }}
      />
    </>
  );
}

function DoctorGrowthScene({ reduceMotion }: { reduceMotion: boolean }) {
  const doctors = [
    { label: 'DR 01', className: 'doctor-one' },
    { label: 'DR 02', className: 'doctor-two' },
    { label: 'DR 03', className: 'doctor-three' },
  ];
  return (
    <div className="doctor-growth-scene">
      <svg aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 920 300">
        {[
          'M460 58 L460 128 L250 220',
          'M460 128 L460 220',
          'M460 128 L670 220',
        ].map((path, index) => (
          <motion.path
            animate={{ pathLength: 1 }}
            d={path}
            fill="none"
            initial={{ pathLength: 0 }}
            key={path}
            stroke={index === 1 ? '#34d399' : '#22d3ee'}
            strokeWidth="3"
            transition={{
              delay: reduceMotion ? 0 : 0.45 + index * 0.65,
              duration: reduceMotion ? 0 : 0.8,
            }}
          />
        ))}
      </svg>
      <motion.div
        animate={{ opacity: 1, scale: 1 }}
        className="doctor-case-root"
        initial={{ opacity: 0, scale: 0.7 }}
      >
        <UserRound />
        <span>同一病例</span>
      </motion.div>
      {doctors.map((doctor, index) => (
        <motion.div
          animate={{ opacity: 1, y: 0 }}
          className={`doctor-contributor ${doctor.className}`}
          initial={{ opacity: 0, y: 20 }}
          key={doctor.label}
          transition={{ delay: reduceMotion ? 0 : 0.7 + index * 0.65 }}
        >
          <Stethoscope />
          <span>{doctor.label}</span>
          <b>新增一条诊断路径</b>
        </motion.div>
      ))}
      <motion.div
        animate={
          reduceMotion
            ? {}
            : {
                boxShadow: [
                  '0 0 0 0 rgba(34,211,238,0)',
                  '0 0 0 12px rgba(34,211,238,.08)',
                  '0 0 0 0 rgba(34,211,238,0)',
                ],
              }
        }
        className="doctor-growth-pulse"
        transition={{ duration: 1.8, repeat: Infinity }}
      >
        <UsersRound />
      </motion.div>
    </div>
  );
}

function ForestFormationScene({ reduceMotion }: { reduceMotion: boolean }) {
  return (
    <div className="forest-formation-scene">
      <motion.div
        animate={{ opacity: 1, scale: 0.72, x: '-230%' }}
        className="mini-diagnosis-tree tree-a"
        initial={{ opacity: 1, scale: 1, x: '0%' }}
        transition={{ duration: reduceMotion ? 0 : 1.35 }}
      >
        <MiniTree index={0} reduceMotion={reduceMotion} />
      </motion.div>
      {['tree-b', 'tree-c', 'tree-d'].map((className, index) => (
        <motion.div
          animate={{ opacity: 1, scale: 0.72, y: 0 }}
          className={`mini-diagnosis-tree ${className}`}
          initial={{ opacity: 0, scale: 0.45, y: 18 }}
          key={className}
          transition={{
            delay: reduceMotion ? 0 : 1 + index * 0.38,
            duration: reduceMotion ? 0 : 0.7,
          }}
        >
          <MiniTree index={index + 1} reduceMotion={reduceMotion} />
        </motion.div>
      ))}
      <motion.div
        animate={{ opacity: 1 }}
        className="forest-formation-label"
        initial={{ opacity: 0 }}
        transition={{ delay: reduceMotion ? 0 : 2.1 }}
      >
        <Trees />
        <span>
          <b>Case Forest</b>每位医生让森林更完整
        </span>
      </motion.div>
    </div>
  );
}

function MiniTree({
  index,
  reduceMotion,
}: {
  index: number;
  reduceMotion: boolean;
}) {
  const delay = reduceMotion ? 0 : index * 0.16;
  return (
    <svg aria-hidden="true" viewBox="0 0 150 150">
      <motion.path
        animate={{ pathLength: 1, opacity: 1 }}
        d="M75 18v32M75 50L36 82M75 50l39 32M36 82v32M114 82v32"
        fill="none"
        initial={{ pathLength: 0, opacity: 0.35 }}
        stroke="currentColor"
        strokeWidth="4"
        transition={{ delay, duration: reduceMotion ? 0 : 1.15 }}
      />
      {[
        [75, 16, 10],
        [75, 50, 9],
        [36, 82, 9],
        [114, 82, 9],
        [36, 118, 9],
        [114, 118, 9],
      ].map(([cx, cy, radius], nodeIndex) => (
        <motion.circle
          animate={{ opacity: 1, scale: 1 }}
          cx={cx}
          cy={cy}
          initial={{ opacity: 0, scale: 0 }}
          key={`${cx}-${cy}`}
          r={radius}
          style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          transition={{
            delay: delay + (reduceMotion ? 0 : 0.16 * nodeIndex),
            type: 'spring',
            stiffness: 180,
            damping: 16,
          }}
        />
      ))}
    </svg>
  );
}

function OrbitNode({
  className,
  delay,
  icon,
  children,
}: {
  className: string;
  delay: number;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      animate={{ opacity: 1, scale: 1 }}
      className={`orbit-node ${className}`}
      initial={{ opacity: 0, scale: 0.75 }}
      transition={{ delay, type: 'spring', stiffness: 190, damping: 18 }}
      whileHover={{ scale: 1.04, y: -3 }}
    >
      <i>{icon}</i>
      <div>{children}</div>
    </motion.div>
  );
}

function LandingStat({ value, label }: { value: string; label: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.65 }}
    >
      <b>{value}</b>
      <span>{label}</span>
    </motion.div>
  );
}
