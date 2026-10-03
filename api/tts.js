export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method not allowed' });
    return;
  }

  const apiKey = process.env.ELEVENLABS_API_KEY;
  const voiceId = process.env.ELEVENLABS_VOICE_ID;

  if (!apiKey || !voiceId) {
    res.status(503).json({ error: 'TTS is not configured' });
    return;
  }

  const text = String(req.body?.text || '').trim();
  if (!text) {
    res.status(400).json({ error: 'Text is required' });
    return;
  }

  if (text.length > 12000) {
    res.status(413).json({ error: 'Text is too long for one render' });
    return;
  }

  const r = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}?output_format=mp3_44100_128`,
    {
      method: 'POST',
      headers: {
        'xi-api-key': apiKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        text,
        model_id: 'eleven_multilingual_v2',
        voice_settings: {
          stability: 0.55,
          similarity_boost: 0.75,
          style: 0.15,
          use_speaker_boost: true
        }
      })
    }
  );

  if (!r.ok) {
    const message = await r.text();
    res.status(r.status).json({ error: 'TTS render failed', details: message.slice(0, 500) });
    return;
  }

  const audio = Buffer.from(await r.arrayBuffer());
  res.setHeader('Content-Type', 'audio/mpeg');
  res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
  res.status(200).send(audio);
}
