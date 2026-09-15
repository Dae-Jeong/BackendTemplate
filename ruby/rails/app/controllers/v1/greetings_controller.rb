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
  end
end
