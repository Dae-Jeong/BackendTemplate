class HealthController < ApplicationController
  def live
    render json: { status: "alive" }
  end

  def ready
    Rails.application.config.x.readiness_check.call
    render json: { status: "ready" }
  rescue ActiveRecord::ConnectionNotEstablished, ActiveRecord::StatementInvalid
    render json: { status: "not_ready" }, status: :service_unavailable
  end
end
