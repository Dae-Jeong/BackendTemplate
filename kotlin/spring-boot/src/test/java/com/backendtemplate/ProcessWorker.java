package com.backendtemplate;

import com.backendtemplate.services.ReservationAttempts;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.TransactionExecution;
import org.springframework.transaction.TransactionExecutionListener;
import tools.jackson.databind.json.JsonMapper;

/** Isolated test process; no fault controls are shipped in the application. */
public class ProcessWorker {
    public static void main(String[] args) throws Exception {
        try (var app = new SpringApplicationBuilder(TemplateApplication.class).web(WebApplicationType.NONE)
                .run("--spring.datasource.url=" + args[0], "--app.environment=test",
                        "--logging.level.root=ERROR", "--logging.level.com.backendtemplate=ERROR")) {
            var manager = app.getBean(JpaTransactionManager.class);
            manager.addListener(new TransactionExecutionListener() {
                @Override
                public void beforeCommit(TransactionExecution transaction) {
                    if (args[3].equals("before")) pause("BEFORE_COMMIT");
                }
                @Override
                public void afterCommit(TransactionExecution transaction, Throwable failure) {
                    if (args[3].equals("after") && failure == null) pause("AFTER_COMMIT");
                }
            });
            System.out.println("WORKER_READY");
            System.out.flush();
            if (System.in.read() < 0) return;
            try {
                var result = app.getBean(ReservationAttempts.class).reserve(args[1], args[2]);
                System.out.println("RESULT:" + JsonMapper.builder().build().writeValueAsString(result));
            } catch (com.backendtemplate.exceptions.ReservationFailure error) {
                System.out.println("ERROR:" + error.getReason().name());
            }
        }
    }

    private static void pause(String marker) {
        System.out.println(marker);
        System.out.flush();
        try {
            System.in.read();
        } catch (java.io.IOException error) {
            throw new IllegalStateException(error);
        }
    }
}
