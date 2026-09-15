class V1::GreetingsController < ApplicationController
  def show
    greeting = GreetingService.call(
      name: params[:name],
      clock: Rails.application.config.x.clock
    )

    render json: {
      data: {
        message: greeting.message,
        generated_at: greeting.generated_at
      }
    }
  rescue GreetingService::InvalidName => error
    render json: {
      type: "about:blank",
      title: "Unprocessable Content",
      status: 422,
      code: "INVALID_INPUT",
      errors: [ { location: [ "query", "name" ], code: error.reason } ]
    }, status: :unprocessable_content, content_type: "application/problem+json"
  end
end
