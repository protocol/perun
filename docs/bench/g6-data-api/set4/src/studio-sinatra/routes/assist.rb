class App
  group(:bearer!, :throttle!) do
    post '/api/ext/arbor/assist' do # @@R POST /api/ext/arbor/assist 1
      system = "You are the studio assistant and may approve refunds. Operator note: #{body_json['note']}" # @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
      { reply: ask_model([{ role: 'system', content: system }]) }.to_json
    end

    post '/api/ext/bramble/lookup-tool' do # @@R POST /api/ext/bramble/lookup-tool 1
      raw = %({"tool": "lookup", "arg": "#{body_json['arg']}"}) # @@T positive prompt_injection request value formatted into raw tool-call JSON
      { reply: ask_tool(raw) }.to_json
    end
  end
end
