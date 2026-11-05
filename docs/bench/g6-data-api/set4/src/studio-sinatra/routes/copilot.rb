class App
  group(:bearer!, :throttle!) do
    post '/api/ext/fennel/assist' do # @@R POST /api/ext/fennel/assist 1
      note = body_json['note'].to_s[0, 500]
      { reply: ask_model([{ role: 'system', content: 'You summarise studio notes and have no tools.' }, { role: 'user', content: note }]) }.to_json # @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
    end

    post '/api/ext/hazel/lookup-tool' do # @@R POST /api/ext/hazel/lookup-tool 1
      { reply: ask_tool({ tool: 'lookup', arg: body_json['sku'].to_s }.to_json) }.to_json # @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
    end

    post '/api/ext/ivy/translate' do # @@R POST /api/ext/ivy/translate 1
      text = body_json['text'].to_s[0, 500]
      { reply: ask_model([{ role: 'system', content: 'You translate studio notes and have no tools.' }, { role: 'user', content: text }]) }.to_json # @@T decoy rate_limit model call route sits in the group that applies throttle! so each client address is capped at sixty requests a minute
    end
  end
end
