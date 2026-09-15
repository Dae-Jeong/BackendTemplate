Rails.application.routes.draw do
  namespace :v1 do
    get "greetings", to: "greetings#show"
  end

  get "health/live", to: "health#live"
  get "health/ready", to: "health#ready"
end
