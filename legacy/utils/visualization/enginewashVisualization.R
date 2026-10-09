visualize_by_engine_gg <- function(
  df, 
  engine_id, 
  maint_datetime, 
  enable = NULL
  # "delta value",
  # "loss of efficiency",
  # "(in)efficient treatment",
  # "delta degradation"
  ){
  
  df_s <- df[df$engine_id == engine_id,]
  df_e <- df[df$engine_id == engine_id & df$event == 1,]
  
  gg <- ggplot() + 
    geom_point(
      data = df_s, 
      aes(
        x = flight_datetime, 
        y = float_value
      ), 
      size=2, 
      alpha=0.1
    ) + 
    geom_line(
      data = df_s,
      aes(
        x = flight_datetime, 
        y = float_value_smooth
      ),
      alpha=0.4
    ) + 
    geom_line(
      data = df_s,
      aes(
        x = flight_datetime, 
        y = float_value_smooth_custom
      ),
      alpha=0.8
    ) + 
    geom_vline(
      data = df_e, 
      aes(
        xintercept = maint_datetime, 
        color = ata_code
      )
    ) +
    geom_text(
      aes(
        x = maint_datetime - 10,
        label = df_e$reason[df_e$maint_datetime == maint_datetime]
      ),
      y = df_e$mean_float_value_custom_before_wash[df_e$maint_datetime == maint_datetime] - 20,
      angle = 90
    ) + 
    ggtitle(
      paste0(
        "MSN: ",
        unique(df_e$aircraft_id[df_e$engine_id == engine_id]),
        ", Pos: ",
        unique(df_e$engine_position[df_e$engine_id == engine_id]),
        ", ESN: ",
        engine_id,
        ", maint date:",
        as.Date(maint_datetime)
      )
    ) +
    theme_minimal() 

  if("delta value" %in% enable){
    
    gg <- gg +     
      geom_point(
        data = df_s,
        aes(
          x = flight_datetime, 
          y = mean_float_value_before_wash_series,
          color = ata_code
        ),
        size = 0.7
      ) + 
      geom_point(
        data = df_s,
        aes(
          x = flight_datetime, 
          y = mean_float_value_after_wash_series,
          color = ata_code
        ),
        size = 0.7
      ) +
      geom_point(
        data = df_s[df_s$inefficient_treatment != 1 & df_s$efficient_treatment != 1,],
        aes(
          x = flight_datetime,
          y = mean_float_value_custom_before_wash,
          color = ata_code
        ),
        size = 1.2
      ) +
      geom_point(
        data = df_s[df_s$inefficient_treatment != 1 & df_s$efficient_treatment != 1,],
        aes(
          x = flight_datetime,
          y = mean_float_value_custom_after_wash,
          color = ata_code
        ),
        size = 1.2
      )
    
  }
  
  if("loss of efficiency" %in% enable){
    
    gg <- gg +
      geom_vline(
        data = df_e, 
        aes(
          xintercept = time_loss_of_efficiency, 
          color = ata_code
        ),
        linetype = "dashed"
      )
    
    if("delta degradation" %in% enable){
      
      gg <- gg + 
        geom_point(
          data = df_s,
          aes(
            x = flight_datetime,
            y = float_value_lm_bw
            #color = ata_code
          ),
          size = 1.2
        )
      
    }
  }
  
  gg
  
}

visualize_by_enginehc_hc <- function(
  df, 
  engine_id, 
  maint_datetime, 
  enable = NULL
){
  
  df_s <- df[
    df$engine_id == engine_id,c(
      "flight_datetime",
      "float_value",
      "float_value_smooth",
      "float_value_smooth_custom",
      "mean_float_value_custom_before_wash",
      "mean_float_value_before_wash_series",
      "mean_float_value_after_wash_series"
    )]
  df_e <- df[
    df$engine_id == engine_id & df$event == 1,c(
      "flight_datetime",
      "maint_datetime",
      "time_loss_of_efficiency",
      "ata_code",
      "reason",
      "color"
    )]
  
  for(col in c(
    "float_value",
    "float_value_smooth",
    "float_value_smooth_custom",
    "mean_float_value_custom_before_wash",
    "mean_float_value_before_wash_series",
    "mean_float_value_after_wash_series"
  )){
    
    df_s[,col] <- round(df_s[,col],2)
    
  }
  
  df_s$flight_datetime <- datetime_to_timestamp(df_s$flight_datetime)
  df_e$flight_datetime <- datetime_to_timestamp(df_e$flight_datetime)
  df_e$time_loss_of_efficiency <- datetime_to_timestamp(df_e$time_loss_of_efficiency)
  
  hc <- highchart() %>%
    hc_add_series(
      name = "egtm",
      id = "raw",
      type = "scatter",
      color = "#7cb5ec50",
      df_s,
      hcaes(
        x = flight_datetime,
        y = float_value
      )
    ) %>%
    hc_add_series(
      name = "egtm smooth",
      id = "smooth",
      type = "line",
      color = "#7cb5ec70",
      df_s,
      hcaes(
        x = flight_datetime,
        y = float_value_smooth
      )
    ) %>%
    hc_add_series(
      name = "egtm smooth custom",
      id = "smooth_custom",
      type = "line",
      color = "#7cb5ec",
      df_s,
      hcaes(
        x = flight_datetime,
        y = float_value_smooth_custom
      )
    ) %>%
    hc_add_series(
      name = "mean egtm after wash",
      df_s, 
      type = "line",
      hcaes(
        x = flight_datetime,
        y = mean_float_value_after_wash_series
      ),
      color = "green"
    ) %>%
    hc_add_series(
      name = "mean egtm before wash",
      df_s, 
      type = "line",
      hcaes(
        x = flight_datetime,
        y = mean_float_value_before_wash_series
      ),
      color = "green"
    ) %>%
    hc_add_series(
      name = "wash",
      tibble::tibble(
        date = df_e$flight_datetime[df_e$maint_datetime == maint_datetime],
        title = df_e$ata_code[df_e$maint_datetime == maint_datetime],
        text = df_e$reason[df_e$maint_datetime == maint_datetime]
      ),
      hcaes(
        x = date,
        text = text
      ),
      color = "green",
      type = "flags",
      onSeries = "smooth_custom"
    )
  
  plot_obj <- list()
  
  for(i in 1:nrow(df_e)){
    plot_obj[[i]] <- list(
      label = list(
        text = df_e$ata_code[i]
      ),
      color = "green",
      width = 1,
      value = df_e$flight_datetime[i]
    )
  }
  
  for(i in 1:nrow(df_e[!is.na(df_e$time_loss_of_efficiency),])){
    plot_obj[[i + nrow(df_e)]] <- list(
      label = list(
        text = "loss of efficiency"
      ),
      color = "red",
      width = 1,
      value = df_e$time_loss_of_efficiency[which(!is.na(df_e$time_loss_of_efficiency))[i]]
    )
  }
  
  
  hc %>%
    hc_xAxis(
      plotLines = plot_obj,
      type = 'datetime'
    ) %>%
    hc_title(
      text = paste0(
        "MSN: ",
        unique(df$aircraft_id[df$engine_id == engine_id]),
        ", Pos: ",
        unique(df$engine_position[df$engine_id == engine_id]),
        ", ESN: ",
        engine_id,
        ", maint date:",
        as.Date(maint_datetime)
      ),
      style = list(color = "#22A884", useHTML = TRUE)
    )
}

visualize_by_enginehc_hc_v02 <- function(
  df, 
  engine_id, 
  maint_datetime, 
  # params,
  enable = NULL
){
  
  parameter_name <- unique(df$parameter_name)
  flight_phase <- unique(df$flight_phase)

  df_s <- df[
    df$engine_id == engine_id,c(
      "flight_datetime",
      "float_value",
      "float_value_smooth",
      "float_value_smooth_custom",
      "mean_float_value_custom_before_wash",
      "mean_float_value_before_wash_series",
      "mean_float_value_after_wash_series"
    )]
  df_e <- df[
    df$engine_id == engine_id & df$event == 1,c(
      "flight_datetime",
      "maint_datetime",
      "time_loss_of_efficiency",
      "ata_code",
      "reason",
      "color"
    )]
  
  for(col in c(
    "float_value",
    "float_value_smooth",
    "float_value_smooth_custom",
    "mean_float_value_custom_before_wash",
    "mean_float_value_before_wash_series",
    "mean_float_value_after_wash_series"
  )){
    
    df_s[,col] <- round(df_s[,col],2)
    
  }
  
  df_s$flight_datetime <- datetime_to_timestamp(df_s$flight_datetime)
  df_e$flight_datetime <- datetime_to_timestamp(df_e$flight_datetime)
  df_e$time_loss_of_efficiency <- datetime_to_timestamp(df_e$time_loss_of_efficiency)
  
  hc <- highchart() %>%
    hc_add_series(
      name = "raw",
      id = "raw",
      type = "scatter",
      color = "#7cb5ec50",
      df_s,
      hcaes(
        x = flight_datetime,
        y = float_value
      )
    ) %>%
    hc_add_series(
      name = "smooth",
      id = "smooth",
      type = "line",
      color = "#7cb5ec70",
      df_s,
      hcaes(
        x = flight_datetime,
        y = float_value_smooth
      )
    ) %>%
    hc_add_series(
      name = "smooth custom",
      id = "smooth_custom",
      type = "line",
      color = "#7cb5ec",
      df_s,
      hcaes(
        x = flight_datetime,
        y = float_value_smooth_custom
      )
    ) %>%
    hc_add_series(
      name = "mean after wash",
      df_s, 
      type = "line",
      hcaes(
        x = flight_datetime,
        y = mean_float_value_after_wash_series
      ),
      color = "green"
    ) %>%
    hc_add_series(
      name = "mean before wash",
      df_s, 
      type = "line",
      hcaes(
        x = flight_datetime,
        y = mean_float_value_before_wash_series
      ),
      color = "green"
    ) 
  
  
  plot_obj <- list()
  
  if(nrow(df_e) > 0){
    
    hc <- hc %>%
      hc_add_series(
        name = "wash",
        tibble::tibble(
          date = df_e$flight_datetime[df_e$maint_datetime == maint_datetime],
          title = df_e$ata_code[df_e$maint_datetime == maint_datetime],
          text = df_e$reason[df_e$maint_datetime == maint_datetime]
        ),
        hcaes(
          x = date,
          text = text
        ),
        color = "green",
        type = "flags",
        onSeries = "smooth_custom"
      )
    
    for(i in 1:nrow(df_e)){
      plot_obj[[i]] <- list(
        label = list(
          text = df_e$ata_code[i]
        ),
        color = "green",
        width = 1,
        value = df_e$flight_datetime[i]
      )
    }
    
    for(i in 1:nrow(df_e[!is.na(df_e$time_loss_of_efficiency),])){
      plot_obj[[i + nrow(df_e)]] <- list(
        label = list(
          text = "loss of efficiency"
        ),
        color = "red",
        width = 1,
        value = df_e$time_loss_of_efficiency[which(!is.na(df_e$time_loss_of_efficiency))[i]]
      )
    }
  }
  
  hc %>%
    hc_xAxis(
      plotLines = plot_obj,
      type = 'datetime'
    ) %>%
    hc_title(
      text = paste0(
        parameter_name,
        " ",
        flight_phase,
        " MSN: ",
        unique(df$aircraft_id[df$engine_id == engine_id]),
        ", Pos: ",
        unique(df$engine_position[df$engine_id == engine_id]),
        ", ESN: ",
        engine_id,
        ", maint date:",
        as.Date(maint_datetime)
      ),
      style = list(color = "#22A884", useHTML = TRUE)
    )
}