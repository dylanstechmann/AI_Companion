import { useState, useCallback } from 'react';

/**
 * useSentiment — Derives emotion from AI response text using keyword analysis.
 *
 * Returns the current emotion and a function to analyze new text.
 * Emotions: 'neutral' | 'happy' | 'sad' | 'excited' | 'thinking' | 'angry'
 *
 * No API cost — runs entirely in the browser.
 */

const EMOTION_RULES = [
  // Order matters — first match wins
  {
    emotion: 'excited',
    keywords: ['amazing', 'awesome', 'incredible', 'wow', 'fantastic', 'yay', 'woohoo', '🎉', '🔥', '✨', '!!!'],
    patterns: [/[!]{2,}/],
  },
  {
    emotion: 'happy',
    keywords: ['happy', 'glad', 'great', 'love', 'wonderful', 'excellent', 'perfect', '😊', '😄', '🙂', '😀', '👍'],
    patterns: [/:\s*\)/],
  },
  {
    emotion: 'sad',
    keywords: ['sorry', 'sad', 'unfortunately', 'regret', 'unfortunate', '😔', '😢', '😞', '💔'],
    patterns: [/:\s*\(/],
  },
  {
    emotion: 'angry',
    keywords: ['angry', 'frustrated', 'ridiculous', 'annoying', 'stupid', '😠', '😡', '🤬'],
    patterns: [],
  },
  {
    emotion: 'thinking',
    keywords: ['hmm', 'let me think', 'interesting', 'perhaps', 'maybe', 'consider', 'wonder', '🤔', '💭'],
    patterns: [/^\?/],
  },
];

export default function useSentiment() {
  const [emotion, setEmotion] = useState('neutral');

  const analyze = useCallback((text) => {
    if (!text || typeof text !== 'string') {
      setEmotion('neutral');
      return 'neutral';
    }

    const lower = text.toLowerCase();
    const first200 = lower.slice(0, 200); // Analyze beginning of response

    for (const rule of EMOTION_RULES) {
      // Check keywords
      for (const kw of rule.keywords) {
        if (first200.includes(kw)) {
          setEmotion(rule.emotion);
          return rule.emotion;
        }
      }
      // Check regex patterns
      for (const pattern of rule.patterns) {
        if (pattern.test(first200)) {
          setEmotion(rule.emotion);
          return rule.emotion;
        }
      }
    }

    // Default: check question marks for "thinking"
    if (first200.includes('?')) {
      setEmotion('thinking');
      return 'thinking';
    }

    setEmotion('neutral');
    return 'neutral';
  }, []);

  const reset = useCallback(() => setEmotion('neutral'), []);

  return { emotion, analyze, reset };
}
