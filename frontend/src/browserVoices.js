// Speech voices can arrive after startup or change while Settings is open.
export function subscribeBrowserVoices(synthesis, onVoices) {
  const update = () => onVoices(synthesis.getVoices());
  synthesis.addEventListener('voiceschanged', update);
  update();
  return () => synthesis.removeEventListener('voiceschanged', update);
}
