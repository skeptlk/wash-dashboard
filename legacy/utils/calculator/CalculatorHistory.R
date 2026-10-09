library(DT)
library(shiny)
library(bs4Dash)
library(shinymanager)
library(shinyjs)
library(dbplyr)
library(dplyr) 
library(DBI)
library(pool)
library(RPostgreSQL)
library(ini)
library(shinyWidgets) 
library(shinycssloaders)
library(highcharter)
library(data.table)
library(shinyscreenshot)
library(xts)
library(reactable)
library(sortable)
library(ggplot2)

library(R6)
library(dplyr)
library(data.table)
library(caTools)
library(RPostgreSQL)


CalculatorHistory <- R6Class(
  
  classname = "CalculatorHistory",
  
  public = list(
    
    df = NA,
    
    df_event = NA,
    
    initialize = function(){
      
      self$df <- NA
      
      self$df_event <- NA
      
    },
    
    process_history = function(
      operator,
      aircraft_type,
      min_flight_datetime,
      max_flight_datetime,
      ata_code,
      flight_phase,
      parameter_name
    ){
      
      self$upload_and_process_wash_data(
        operator,
        aircraft_type,
        min_flight_datetime,
        max_flight_datetime,
        ata_code,
        flight_phase,
        parameter_name
      )
      
      self$df <- self$df[with(self$df, order(engine_id,flight_datetime)),]
      
      self$df <- do.call(rbind, lapply(unique(self$df$engine_id), function(esn){
        
        df_esn <- self$df[self$df$engine_id == esn,]
        
        df_esn <- self$process_sv(df_esn)
        
        df_esn <- self$process_event(df_esn)
        
        df_esn <- self$process_params_smooth(df_esn)
        
        df_esn <- self$process_params_mean(df_esn)
        
        # df_esn <- self$process_params_clear_from_wash(df_esn)
        #   
        # df_esn <- self$process_params_linear_bw(df_esn)
        
        df_esn
        
      }))
      
      self$process_df_event(
        min_flight_datetime,
        max_flight_datetime
      )
       
      # self$upload_amos_ac_utilization()
      
    },
    
    upload_and_process_wash_data = function(
      operator,
      aircraft_type,
      min_flight_datetime,
      max_flight_datetime,
      ata_code,
      flight_phase,
      parameter_name
    ){
      
      config_list <- read.ini( 
        './config/config.ini',
        encoding = getOption("encoding")
      )
      
      pool <- dbPool(
        drv = dbDriver("PostgreSQL"),
        dbname = config_list$PROJECT_DB_ECM_NEW$dbname,
        host =  config_list$PROJECT_DB_ECM_NEW$host,
        port = config_list$PROJECT_DB_ECM_NEW$port,
        user = config_list$PROJECT_DB_ECM_NEW$user,
        password = config_list$PROJECT_DB_ECM_NEW$psw
      )
      
      onStop(function() {
        poolClose(pool)
      })
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator == !! operator, #"s7",
          aircraft_type == !!aircraft_type #"CFM56-7"
        ) %>%
        collect()
      
      engine_raw_output <- pool %>%
        tbl(in_schema("ecmapp", "engine_raw_output_mv")) %>%
        filter(
          engine_id %in% !!unique(fleetsummary$engine_id), 
          parameter_name == !!parameter_name, #"EGTHDM",
          flight_phase == !!flight_phase, #"TAKEOFF",
          flight_datetime >= !!min_flight_datetime, #as.Date('2022-10-01'),
          flight_datetime <= !!max_flight_datetime #as.Date('2023-06-01')
        ) %>%
        collect()
      
      engine_smooth <- pool %>%
        tbl(in_schema("s7_mdb", "engine_smooth")) %>%
        filter(
          aircraft_id %in% !!unique(fleetsummary$aircraft_id), 
          parameter_name == !!parameter_name, #"EGTHDM",
          flight_phase == !!flight_phase, #"TAKEOFF",
          flight_datetime >= !!min_flight_datetime, #as.Date('2022-10-01'),
          flight_datetime <= !!max_flight_datetime #as.Date('2023-06-01')
        ) %>%
        collect()
      
      maintenance <- pool %>%
        tbl(in_schema("ecmapp", "maintenance")) %>%
        filter(
          engine_id %in% !!unique(engine_raw_output$engine_id),
          ata_code %in% !!ata_code,
          maint_datetime >= !!min_flight_datetime, #as.Date('2022-10-01'),
          maint_datetime <= !!max_flight_datetime #as.Date('2023-06-01')
        )  %>%
        collect() %>%
        left_join(
          pool %>%
            tbl(in_schema("ecmapp", "atacodecolor_operator")) %>%
            filter(
              operator == !!operator,
              ata_code %in% !!ata_code
            ) %>%
            select(
              ata_code,
              color
            ) %>%
            collect(),
          by = c(
            "ata_code" = "ata_code"
          )
        )
      
      engine_raw_output <- engine_raw_output[
        ,setdiff(
          colnames(engine_raw_output),
          c(
            "integer_value",
            "char_value",
            "parameter_name"
          )
        )]
      
      engine_smooth <- engine_smooth[
        ,setdiff(
          colnames(engine_raw_output),
          c(
            "engine_id"
          )
        )]
      
      engine_raw_output <- engine_raw_output[
        !duplicated(engine_raw_output),
        ]
      engine_smooth <- engine_smooth[
        !duplicated(engine_smooth),
        ]
      
      df <- engine_raw_output %>%
        left_join(
          engine_smooth,
          by = c(
            "aircraft_id" = "aircraft_id",
            "engine_position" = "engine_position",
            "flight_phase" = "flight_phase",
            "flight_datetime" = "flight_datetime"
          )
        )
      
      colnames(df)[
        colnames(df) == "float_value.x"
        ] <- "float_value"
      
      colnames(df)[
        colnames(df) == "float_value.y"
        ] <- "float_value_smooth"
      
      df_events <- maintenance[
        maintenance$ata_code %in% ata_code,
        setdiff(
          colnames(maintenance),
          c(
            "ata_classification",
            "family",
            "author",
            "creation_datetime"
          )
        )
        ]
      
      ###
      # Join event to 
      ###
      
      df$maint_datetime <- as.POSIXct(NA)
      df$ata_code <- as.character(NA)
      df$reason <- NA
      df$color <- NA
      df$event <- 0
      
      
      df_events$flight_datetime_before_wash <- as.POSIXct(NA)
      df_events$flight_datetime_after_wash <- as.POSIXct(NA)
      
      df <- df[with(df, order(engine_id, flight_datetime)),]
      
      for(i in 1:nrow(df_events)){
        
        df_events$flight_datetime_before_wash[i] <- max(df$flight_datetime[
          df$engine_id == df_events$engine_id[i] & 
            df$flight_datetime <= df_events$maint_datetime[i]
          ], na.rm = TRUE)
        
        df_events$flight_datetime_after_wash[i] <- min(df$flight_datetime[
          df$engine_id == df_events$engine_id[i] & 
            df$flight_datetime > df_events$maint_datetime[i] 
          ], na.rm = TRUE)
        
        df$maint_datetime[
          df$engine_id == df_events$engine_id[i] & 
            df$flight_datetime == df_events$flight_datetime_after_wash[i]
          ] <- df_events$maint_datetime[i]
        
        df$ata_code[
          df$engine_id == df_events$engine_id[i] & 
            df$flight_datetime == df_events$flight_datetime_after_wash[i]
          ] <- df_events$ata_code[i]
        
        df$reason[
          df$engine_id == df_events$engine_id[i] & 
            df$flight_datetime == df_events$flight_datetime_after_wash[i]
          ] <- df_events$reason[i]
        
        df$color[
          df$engine_id == df_events$engine_id[i] & 
            df$flight_datetime == df_events$flight_datetime_after_wash[i]
          ] <- df_events$color[i]
        
        df$event[df$engine_id == df_events$engine_id[i] & 
                   df$flight_datetime == df_events$flight_datetime_after_wash[i]
                 ] <- 1
        
      }
      
      self$df <- df
      
    },
    
    process_sv = function(df_esn){
      
      # df_esn$sv_event <- 0
      # 
      # df_esn$sv_event[diff(df_esn$flight_datetime, units = "mins")/(60*24) >= 70] <- 1
      # 
      # df_esn$sv_event_cum <- cumsum(df_esn$sv_event)
      
      df_esn
      
    },
    
    process_event = function(df_esn){
      
      # df_esn <- df_esn[with(df_esn, order(time)),]
      # 
      # df_esn$event_type[which(df_esn$sv_event == 1)] <- "overhaul"
      # 
      # df_esn$event <- 0
      # 
      # idx_sv <- which(df_esn$event_type != "")
      # 
      # if(max(idx_sv + 1) >  length(df_esn$event)){
      #   idx_sv[length(idx_sv)] <- idx_sv[length(idx_sv)] - 1
      # }
      # 
      # df_esn$event[idx_sv + 1] <- 1
      
      df_esn <- df_esn[with(df_esn, order(flight_datetime)),]
      
      df_esn$event_cum <- cumsum(df_esn$event)
      
      df_esn
      
    },
    
    process_params_smooth = function(df_esn){
      
      do.call(rbind, lapply(unique(df_esn$event_cum), function(event_cum){
        
        df_esn_event <- df_esn[which(df_esn$event_cum == event_cum),]
        
        df_esn_event$float_value_smooth[
          is.na(df_esn_event$float_value_smooth)
          ] <- df_esn_event$float_value[
            is.na(df_esn_event$float_value_smooth)
            ]
        
        df_esn_event$float_value_smooth_custom <- runmean(
          x = df_esn_event$float_value_smooth,
          k = 30,
          align = "center"
        )
        
        # if(all(is.na(df_esn_event$float_value_smooth))){
        #   
        #   df_esn_event$float_value_smooth_custom <- runmean(
        #     x = df_esn_event$float_value,
        #     k = 60,
        #     align = "center"
        #   )
        #   
        # }
        
        df_esn_event
        
      }))
      
    },
    
    process_params_mean = function(df_esn){
      
      do.call(rbind, lapply(unique(df_esn$event_cum), function(event_cum){
        
        df_esn_event <- df_esn[which(df_esn$event_cum == event_cum),]
        
        df_esn_event$mean_float_value_custom_before_wash <- NA 
        df_esn_event$mean_float_value_custom_after_wash <- NA
        df_esn_event$delta_float_value_custom <- NA
        df_esn_event$mean_float_value_before_wash_series <- NA
        df_esn_event$mean_float_value_after_wash_series <- NA
        df_esn_event$time_loss_of_efficiency <- as.POSIXct(NA)
        df_esn_event$event_loss_of_efficiency <- 0
        df_esn_event$inefficient_treatment <- 0
        df_esn_event$efficient_treatment <- 0
        df_esn_event$cycles_inefficient_treatment <- 0
        df_esn_event$cycles_efficient_treatment <- 0
        # browser()
        if(event_cum > 0 & nrow(df_esn_event) > 0){
          
          df_esn_event_prev <- df_esn[which(df_esn$event_cum == event_cum - 1),]
          if(nrow(df_esn_event_prev) > 0){  
          df_esn_event_prev <- df_esn_event_prev[with(df_esn_event_prev, order(flight_datetime)),]
          
          mean_float_value_custom_before_wash <- min(
            tail(
              df_esn_event_prev$float_value_smooth_custom, 
              15
            )
          )
          mean_float_value_custom_after_wash <- max(
            head(
              df_esn_event$float_value_smooth_custom, 
              15
            )
          )
          
          df_esn_event$mean_float_value_custom_before_wash <- mean_float_value_custom_before_wash
          df_esn_event$mean_float_value_custom_after_wash <- mean_float_value_custom_after_wash
          df_esn_event$ata_code <- df_esn_event$ata_code[!is.na(df_esn_event$ata_code)]
          df_esn_event$color <- df_esn_event$color[!is.na(df_esn_event$color)]
          
          df_esn_event$delta_float_value_custom <- mean_float_value_custom_after_wash - mean_float_value_custom_before_wash
          
          df_esn_event$mean_float_value_before_wash_series <- mean_float_value_custom_before_wash
          df_esn_event$mean_float_value_after_wash_series <- mean_float_value_custom_after_wash
          
          # browser()
          
          if(
            nrow(
              df_esn_event[
                df_esn_event$float_value_smooth_custom <= mean_float_value_custom_before_wash - 2,
                ]) > 0
            ){
            
            time_loss_of_efficiency <- head(
              df_esn_event$flight_datetime[
                df_esn_event$float_value_smooth_custom <= mean_float_value_custom_before_wash - 2
                ],
              1
            )
            df_esn_event$event_loss_of_efficiency[
              df_esn_event$flight_datetime == time_loss_of_efficiency
              ] <- 1
            
            df_esn_event$time_loss_of_efficiency <- time_loss_of_efficiency
            
            df_esn_event$mean_float_value_before_wash_series[
              df_esn_event$flight_datetime > time_loss_of_efficiency
              ] <- NA
            
            df_esn_event$mean_float_value_after_wash_series[
              df_esn_event$flight_datetime > time_loss_of_efficiency
              ] <- NA
            
            df_esn_event$ata_code[
              df_esn_event$flight_datetime > time_loss_of_efficiency
              ] <- NA
            
            df_esn_event$color[
              df_esn_event$flight_datetime > time_loss_of_efficiency
              ] <- NA
            
            df_esn_event$inefficient_treatment[
              df_esn_event$flight_datetime >= time_loss_of_efficiency
              ] <- 1
            
            df_esn_event$efficient_treatment[
              df_esn_event$flight_datetime <= time_loss_of_efficiency
              ] <- 1
            
          }
          else{
            
            df_esn_event$mean_float_value_before_wash_series <- NA
            df_esn_event$mean_float_value_after_wash_series <- NA
            df_esn_event$time_loss_of_efficiency <- NA
            
          }
          
        }
        }
        
        df_esn_event$cum_event_loss_of_efficiency <- cumsum(df_esn_event$event_loss_of_efficiency)
        
        df_esn_event
        
      }))
      
    },
    
    process_params_clear_from_wash = function(df_esn){
      
      # if("overhaul" %in% unique(df_esn$event_type)){
      #   
      #   cum_event_overhaul <- unique(df_esn$event_cum[which(df_esn$event_type == "overhaul")]) + 1
      #   df_esn$delta_egtm[df_esn$event_cum %in% cum_event_overhaul] <- 0
      #   df_esn$delta_delta_fuel_flow_smooth[df_esn$event_cum %in% cum_event_overhaul] <- 0
      #   
      # }
      
      df_esn$float_value_smooth_custom_cfw <- df_esn$float_value_smooth_custom
      
      df_esn$float_value_smooth_custom_cfw[df_esn$event_cum > 0] <-
        df_esn$float_value_smooth_custom[df_esn$event_cum > 0] -
        df_esn$event_cum[df_esn$event_cum > 0]*
        mean(
          df_esn$delta_float_value_custom[df_esn$event_cum > 0], 
          na.rm = T
        )
      
      df_esn$float_value_smooth_custom_cfow <- df_esn$float_value_smooth_custom
      
      df_esn$float_value_smooth_custom_cfow[
        df_esn$event_cum > 0 & 
          !is.na(df_esn$delta_float_value_custom)
        ] <- df_esn$float_value_smooth_custom[
          df_esn$event_cum > 0 & 
            !is.na(df_esn$delta_float_value_custom)
          ] - 
        df_esn$delta_float_value_custom[
          df_esn$event_cum > 0 & 
            !is.na(df_esn$delta_float_value_custom)
          ]
      
      df_esn$float_value_delta_fact_cfow <- df_esn$float_value_smooth_custom - df_esn$float_value_smooth_custom_cfow
      
      df_esn
      
    },
    
    process_params_linear_bw = function(df_esn){
      
      df_esn_proc <- do.call(rbind, lapply(unique(df_esn$event_cum), function(event_cum){
        
        df_esn_event <- df_esn[which(df_esn$event_cum == event_cum),]
        
        df_esn_event <- df_esn_event[with(df_esn_event, order(flight_datetime)),]
        
        df_esn_event$float_value_lm_bw <- NA
        df_esn_event$float_value_cfw_lm_bw <- NA
        df_esn_event$float_value_cfow_lm_bw <- NA
        
        x <- seq_along(df_esn_event$flight_datetime)
        
        idx_float_value_nna <- which(
          !is.na(df_esn_event$float_value_smooth_custom)
        )
        
        if(event_cum == 0){
          
          df_esn_event$float_value_lm_bw[
            idx_float_value_nna
            ] <- predict(lm(df_esn_event$float_value_smooth_custom[
              idx_float_value_nna
              ] ~ x[
                idx_float_value_nna
                ]))
          df_esn_event$float_value_cfw_lm_bw[
            idx_float_value_nna
            ] <- predict(lm(df_esn_event$float_value_smooth_custom_cfw[
              idx_float_value_nna
              ] ~ x[
                idx_float_value_nna
                ]))
          df_esn_event$float_value_cfow_lm_bw[
            idx_float_value_nna
            ] <- predict(lm(df_esn_event$float_value_smooth_custom_cfow[
              idx_float_value_nna
              ] ~ x[
                idx_float_value_nna
                ]))
          
        }
        else{
          
          intercept_float_value_smooth <-  mean(
            tail(
              df_esn$float_value_smooth_custom[which(df_esn$event_cum == event_cum - 1)],
              5
            ),
            na.rm = T
          )
          
          intercept_float_value_smooth_cfw <- mean(
            tail(
              df_esn$float_value_smooth_custom_cfw[which(df_esn$event_cum == event_cum - 1)],
              5
            ),
            na.rm = T
          )
          
          intercept_float_value_smooth_cfow <- mean(
            tail(
              df_esn$float_value_smooth_custom[which(df_esn$event_cum == event_cum - 1)],
              5
            ),
            na.rm = T
          )
          
          if(
            is.na(intercept_float_value_smooth) 
            #|"overhaul" %in% unique(df_esn$event_type[which(df_esn$event_cum == event_cum - 1)]) 
          ){
            
            intercept_float_value_smooth <- mean(
              head(
                df_esn$float_value_smooth_custom[which(df_esn$event_cum == event_cum)],
                5
              ),
              na.rm = T
            )
            
          }
          
          if(
            is.na(intercept_float_value_smooth_cfw) 
            #|"overhaul" %in% unique(df_esn$event_type[which(df_esn$event_cum == event_cum - 1)]) 
          ){
            
            intercept_float_value_smooth_cfw <- mean(
              head(
                df_esn$float_value_smooth_custom_cfw[which(df_esn$event_cum == event_cum)],
                5
              ),
              na.rm = T
            )
            
          }
          
          if(
            is.na(intercept_float_value_smooth_cfow) 
            # |"overhaul" %in% unique(df_esn$event_type[which(df_esn$event_cum == event_cum - 1)])
          ){
            
            intercept_float_value_smooth_cfow <- mean(
              head(
                df_esn$float_value_smooth_custom_cfow[which(df_esn$event_cum == event_cum)],
                5
              ),
              na.rm = T
            )
            
          }
          
          
          df_esn_event$float_value_lm_bw[idx_float_value_nna] <- private$predict_lm_intercept(
            target = df_esn_event$float_value_smooth_custom[idx_float_value_nna],
            feature = x[idx_float_value_nna],
            intercept = intercept_float_value_smooth,
            new_feature = x[idx_float_value_nna]
          )
          
          
          df_esn_event$float_value_cfw_lm_bw[idx_float_value_nna] <- private$predict_lm_intercept(
            target = df_esn_event$float_value_smooth_custom_cfw[idx_float_value_nna],
            feature = x[idx_float_value_nna],
            intercept = intercept_float_value_smooth_cfw,
            new_feature = x[idx_float_value_nna]
          )
          
          
          df_esn_event$float_value_cfow_lm_bw[idx_float_value_nna] <- private$predict_lm_intercept(
            target = df_esn_event$float_value_smooth_custom_cfow[idx_float_value_nna],
            feature = x[idx_float_value_nna],
            intercept = intercept_float_value_smooth_cfow,
            new_feature = x[idx_float_value_nna]
          )
            
        }
        
        df_esn_event
        
      }))
      
      df_esn_proc
      
    },
    
    process_df_event = function(min_flight_datetime, max_flight_datetime){
      
      df_e <- self$df[!is.na(self$df$maint_datetime),]
      
      df_e$maint_date <- as.Date(df_e$maint_datetime)
      
      df_e <- df_e[with(df_e , order(maint_datetime)),]
      
      df_e$id_wash <- 1:nrow(df_e)
      
      config_list <- read.ini( 
        './config/config.ini',
        encoding = getOption("encoding")
      )
      
      pool <- dbPool(
        drv = dbDriver("PostgreSQL"),
        dbname = config_list$PROJECT_DB_ECM_NEW$dbname,
        host =  config_list$PROJECT_DB_ECM_NEW$host,
        port = config_list$PROJECT_DB_ECM_NEW$port,
        user = config_list$PROJECT_DB_ECM_NEW$user,
        password = config_list$PROJECT_DB_ECM_NEW$psw
      )
      
      onStop(function() {
        poolClose(pool)
      })
      
      aircrafts_names <- pool %>%
        tbl(in_schema("s7", "_aircrafts_names")) %>% 
        filter(
          ac_serial %in% !!unique(df_e$aircraft_id)
        ) %>%
        collect()
      
      ac_utilization <- pool %>% 
        tbl(in_schema("s7", "fake_amos_ac_utilization")) %>% 
        filter(
          ac_registr %in% !!substr(unique(aircrafts_names$ac_reg_new),4,nchar(unique(aircrafts_names$ac_reg_new))),
          # departure_datetime >= as.Date('2022-10-01'),
          # arrival_datetime <= as.Date('2023-06-01')
          departure_datetime >= !!min_flight_datetime,
          arrival_datetime <= !!max_flight_datetime
        ) %>%
        collect()
      
      ac_utilization <- ac_utilization[with(ac_utilization, order(ac_registr, departure_datetime)),]
      
      ac_utilization$departure_date <- as.Date(ac_utilization$departure_datetime)
      ac_utilization$arrival_date <- as.Date(ac_utilization$arrival_datetime)
      
      ac_utilization$departure_arrival <- paste0(ac_utilization$departure, "->", ac_utilization$arrival)
      
      ac_utilization_gr <- ac_utilization %>%
        group_by(
          ac_registr,
          departure_date
          #,arrival_date
        ) %>% 
        summarise(
          fn_numbers = paste0(fn_number, collapse = ","),
          flights = paste0(departure_arrival, collapse = ","),
          departures = paste0(departure, collapse = ","),
          arrivals = paste0(arrival, collapse = ","),
          tah = min(tah),
          tac = min(tac)
        )
      
      df_e <- df_e %>%
        left_join(
          aircrafts_names,
          by = c(
            "aircraft_id" = "ac_serial"
          )
        )
      
      df_e$ac_registr <- substr(df_e$ac_reg_new,4,nchar(df_e$ac_reg_new))
      
      df_e <- df_e %>%
        left_join(
          ac_utilization_gr,
          by = c(
            "ac_registr" = "ac_registr",
            "maint_date" = "departure_date"
          )
        )
      
      ac_utilization_gr <- ac_utilization_gr[,c("ac_registr", "departure_date","tah","tac")]
      
      colnames(ac_utilization_gr)[
        colnames(ac_utilization_gr) == "tac"
        ] <- "tac_loss_of_efficiency"
      
      colnames(ac_utilization_gr)[
        colnames(ac_utilization_gr) == "tah"
        ] <- "tah_loss_of_efficiency"
      
      df_e$date_loss_of_efficiency <- as.Date(df_e$time_loss_of_efficiency)
      
      df_e <- df_e %>%
        left_join(
          ac_utilization_gr,
          by = c(
            "ac_registr" = "ac_registr",
            "date_loss_of_efficiency" = "departure_date"
          )
        )
      
      
      df_e$cyc_loss_off_efficiency <- df_e$tac_loss_of_efficiency - df_e$tac
      
      df_e$hrs_loss_off_efficiency <- (df_e$tah_loss_of_efficiency - df_e$tah)/60
      
      self$df_event <- df_e
      
    }
    
  ),
  
  private = list(
    
    predict_lm_intercept = function(
      target,
      feature,
      intercept,
      new_feature
    ){
      
      model <- lm(
        I(target - intercept) ~ 0 + feature
      )
      
      prediction <- intercept + model$coefficients * new_feature
      
      prediction 
      
    }
    
  )
)