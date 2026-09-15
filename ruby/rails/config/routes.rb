Rails.application.routes.draw do
  namespace :v1 do
    get "greetings", to: "greetings#show"
    post "reservations", to: "reservations#create"
    get "reservations/:reservation_id", to: "reservations#show"
  end

  get "health/live", to: "health#live"
  get "health/ready", to: "health#ready"
end
