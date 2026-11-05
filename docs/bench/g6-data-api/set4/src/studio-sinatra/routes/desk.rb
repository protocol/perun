class App
  group(:bearer!) do
    post '/api/ext/quill/summarise' do # @@R POST /api/ext/quill/summarise 1
      note = body_json['note'].to_s[0, 500]
      reply = ask_model([{ role: 'system', content: 'You summarise studio notes and have no tools.' }, { role: 'user', content: note }]) # @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
      { reply: reply }.to_json
    end
  end
end
