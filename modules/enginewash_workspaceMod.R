enginewash_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("enginewash_workspace"))
  
}

enginewash_workspaceMod <- function(input, output, session, credentials, headerselectors, pool, id_tab) {
  
  ns <- session$ns
  
  enginewash_data <- reactiveValues(
    df = NULL,
    df_event = NULL,
    list_calchist_df = NULL,
    list_calchist_df_event = NULL
  )
  
  output$enginewash_operator <- renderUI({
    
    ns <- session$ns
    
    fleetsummary <- pool %>% tbl(in_schema("ecmapp", "_fleetsummary")) %>% collect()
    
    pickerInput(
      ns("enginewash_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), # "utair",
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = "s7", #"utair",
      multiple = F
    )  
    
  })
  
  output$enginewash_actype <- renderUI({
    
    ns <- session$ns
    
    choices <- NULL
    
    choicesOpt <- NULL
    
    df_choices <- NULL
    
    if(!is.null(input$enginewash_operator_pi)){
      
      df_choices <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$enginewash_operator_pi
        ) %>%
        group_by(
          operator,
          aircraft_type
        ) %>%
        summarise(
          count_ac = n_distinct(aircraft_id)
        ) %>%
        collect()
      
      
      df_choices <- df_choices[!(df_choices$aircraft_type %in% c(
        "ERJ175", "A330-200","A320-271 NEO","A321-271 NEO","A321-271 NX"
      )),] #,"B777-300ER"
      
      choices <- lapply(split(df_choices$aircraft_type, df_choices$operator), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(df_choices$count_ac, df_choices$operator), as.list))
      )
      
    }
    
    pickerInput(
      ns("enginewash_actype_pi"),
      label = "A/C Type:", 
      choices = choices,
      choicesOpt = choicesOpt, 
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected = "B737-800",#selected,#"ATR72-212",
      multiple = F
    )
    
  })
  
  output$enginewash_acreg <- renderUI({
    
    ns <- session$ns
    
    choices <- NULL
    
    choicesOpt <- NULL
    
    if(!is.null(input$enginewash_operator_pi) & !is.null(input$enginewash_actype_pi)){
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$enginewash_operator_pi,
          aircraft_type %in% !!input$enginewash_actype_pi,
          !is.na(ac_reg_new),
          !is.na(aircraft_type),
          ac_reg_new != "-"
        ) %>%
        collect()
      
      fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
      
      fleetsummary <- fleetsummary %>% 
        group_by(
          aircraft_id, 
          engine_position
        ) %>%
        filter(
          install_datetime == max(install_datetime)
        )
      
      if(nrow(fleetsummary) > 0){
        
        df_choices <- fleetsummary[,c(
          "aircraft_type",
          "ac_reg_new",
          "ac_reg_old",
          "aircraft_id",
          "engine_position",
          "engine_id"
        )] %>%
          group_by(
            aircraft_type,
            ac_reg_new,
            ac_reg_old,
            aircraft_id
          ) %>%
          tidyr::pivot_wider(
            names_from = engine_position,
            names_prefix = "esn_",
            values_from = c(
              engine_id
            )
          ) %>%
          mutate(
            subtext = paste0(
              ac_reg_old,
              " ",
              aircraft_id,
              ", pos.1: ",
              esn_1,
              ", pos.2: ",
              esn_2
            )
          )
        
        choices <- lapply(split(df_choices$ac_reg_new, df_choices$aircraft_type), as.list)
        
        choicesOpt <- list(
          subtext = unlist(lapply(split(df_choices$subtext, df_choices$aircraft_type), as.list))
        )
        
      }
      
      pickerInput(
        ns("enginewash_acreg_pi"),
        label = "A/C Reg:", 
        choices = choices,
        choicesOpt = choicesOpt, 
        options = list(
          `live-search`=TRUE,
          `actions-box` = TRUE,
          `deselect-all-text` = "deselect",
          `select-all-text` = "select all",
          `none-selected-text` = "zero"
        ),
        selected = df_choices$ac_reg_new,
        multiple = T
      ) 
    }
    
  })
  
  output$enginewash_atacode <- renderUI({
    
    ns <- session$ns
    
    if(!is.null(input$enginewash_actype_pi)){
      
      atacode <- pool %>%
        tbl(in_schema("ecmapp", "atacodecolor_operator")) %>%
        filter(
          operator %in% !!input$enginewash_operator_pi
        ) %>%
        collect()
      
      pickerInput(
        ns("pi_enginewash_atacode"),
        label = "Ata code",
        choices = atacode$ata_code,
        choicesOpt = list(
          subtext = atacode$description
        ),
        selected = c(
          "206",
          "207",
          "209"
        ),
        options = list(
          `live-search`=TRUE
        ),
        multiple = T
      ) 
    }
    
  })
  
  output$enginewash_parameter_takeoff <- renderUI({
    
    parameters <- pool %>%
      tbl(in_schema("ecmapp", "parameters")) %>%
      filter(
        aircraft_type %in% !!input$enginewash_actype_pi,
        flight_phase == !!"TAKEOFF"
      ) %>%
      collect()
    
    parameters <- parameters[!duplicated(parameters),]
    
    parameters <- parameters[with(parameters, order(table_name, parameter_name)),]
    
    choices <- lapply(split(parameters$parameter_name, parameters$table_name), as.list)
    
    choicesOpt <- list(
      subtext = unlist(lapply(split(parameters$param_description, parameters$table_name), as.list))
    )
    
    pickerInput(
      ns("enginewash_parameters_takeoff_pi"),
      label = "Parameters TAKEOFF",
      choices = choices,
      choicesOpt = choicesOpt,
      options = list(
        `live-search`=TRUE
      ),
      selected = "EGTHDM",
      multiple = F
    )
    
  })
  
  output$enginewash_details_table <- DT::renderDataTable(server = FALSE,{
    
    req(enginewash_data$df_event)
    
    if (is.null(enginewash_data$df_event)){
      return()
    }
    else{
      
      color_from_middle <- function (data, color1,color2) 
      {
        max_val=max(abs(data))
        JS(sprintf("isNaN(parseFloat(value)) || value < 0 ? 'linear-gradient(90deg, transparent, transparent ' + (50 + value/%s * 50) + '%%, %s ' + (50 + value/%s * 50) + '%%,%s  50%%,transparent 50%%)': 'linear-gradient(90deg, transparent, transparent 50%%, %s 50%%, %s ' + (50 + value/%s * 50) + '%%, transparent ' + (50 + value/%s * 50) + '%%)'",
                   max_val,color1,max_val,color1,color2,color2,max_val,max_val))
      } 

      DT::datatable({
        enginewash_data$df_event
      },
      caption = "Event table",
      extensions = 'Buttons',
      options = list(
        paging = TRUE,
        dom = 'Bfrtip',
        buttons = list(
          list(
            extend = 'collection',
            buttons = c('csv', 'excel'),
            exportOptions = list(
              modifiers = list(page = "all")
            )
          )
        ),
        columnDefs=list(list(className='dt-center',targets="_all")
        ),
        scrollX = TRUE
      ),
      filter = "top",
      selection = 'single',
      class = 'hover', 
      rownames = FALSE
      ) %>%
        formatStyle(
          'delta_EGTHDM_TAKEOFF',
          background = color_from_middle(
            enginewash_data$df_event$delta_EGTHDM_TAKEOFF,
            'orange',
            'lightblue'
          ),
          backgroundSize = '100% 90%',
          backgroundRepeat = 'no-repeat',
          backgroundPosition = 'center'
        ) %>%
        formatStyle(
          'delta_GWFM_CRUISE',
          background = color_from_middle(
            enginewash_data$df_event$delta_GWFM_CRUISE,
            'orange',
            'lightblue'
          ),
          backgroundSize = '100% 90%',
          backgroundRepeat = 'no-repeat',
          backgroundPosition = 'center'
        ) %>%
        formatStyle(
          'delta_DEGT_CRUISE',
          background = color_from_middle(
            enginewash_data$df_event$delta_DEGT_CRUISE,
            'orange',
            'lightblue'
          ),
          backgroundSize = '100% 90%',
          backgroundRepeat = 'no-repeat',
          backgroundPosition = 'center'
        ) 
    }
    
  })
  
  output$enginewash_details_plot <- renderPlot({
    
    req(input$enginewash_details_table_rows_selected)
    
    if(
      !is.null(enginewash_data$df) & 
      !is.null(input$enginewash_details_table_rows_selected) 
      #&!is.null(input$cgi_enable)
    ){
      
      visualize_by_engine_gg(
        df = enginewash_data$df,
        engine_id = enginewash_data$df_event$engine_id[input$enginewash_details_table_rows_selected],
        maint_datetime = enginewash_data$df_event$maint_datetime[input$enginewash_details_table_rows_selected],
        enable = NULL #input$cgi_enable
      )
      
    }
    
  })
  
  output$enginewash_details_plot_hc <- renderUI({
    
    req(input$enginewash_details_table_rows_selected)
    
    if(
      # !is.null(enginewash_data$df) & 
      !is.null(input$enginewash_details_table_rows_selected) 
      # & !is.null(input$cgi_enable)
    ){
      
      list_hc <- list()
      
      df_event <- enginewash_data$list_calchist_df_event[[as.character(1)]]
      
      for(i in 1:length(enginewash_data$list_calchist_df)){
        
        list_hc[[i]] <- visualize_by_enginehc_hc_v02(
          df = enginewash_data$list_calchist_df[[as.character(i)]],
          engine_id = enginewash_data$df_event$engine_id[input$enginewash_details_table_rows_selected],
          maint_datetime = enginewash_data$df_event$maint_datetime[input$enginewash_details_table_rows_selected],
          #params[i,],
          enable = NULL
        )
        
      }
      
      hw_grid(
        list_hc,
        rowheight = 740,
        ncol = 1
      )
      
    }
    
  })
  
  output$enginewash_summary_table <- DT::renderDataTable(server = FALSE,{
    
    req(enginewash_data$df_event)
    
    if (is.null(enginewash_data$df_event)){
      return()
    }
    else{

      df_g <- as.data.frame(
        as.matrix(
          t(
            enginewash_data$df_event %>%
              group_by(ata_code) %>%
              summarise(
                count_washes = n(),
                count_engines = n_distinct(engine_id),
                mean_delta_GWFM_CRUISE = round(mean(delta_GWFM_CRUISE, na.rm = T),2),
                mean_cyc_loe_GWFM_CRUISE = round(mean(cyc_loe_GWFM_CRUISE, na.rm = T)),
                mean_hrs_loe_GWFM_CRUISE = round(mean(hrs_loe_GWFM_CRUISE, na.rm = T)),
                mean_days_loe_GWFM_CRUISE = round(mean(days_loe_GWFM_CRUISE, na.rm = T)),
                mean_delta_DEGT_CRUISE = round(mean(delta_DEGT_CRUISE, na.rm = T),2),
                mean_cyc_loe_DEGT_CRUISE = round(mean(cyc_loe_DEGT_CRUISE, na.rm = T)),
                mean_hrs_loe_DEGT_CRUISE = round(mean(hrs_loe_DEGT_CRUISE, na.rm = T)),
                mean_days_loe_DEGT_CRUISE = round(mean(days_loe_DEGT_CRUISE, na.rm = T)),
                mean_delta_EGTHDM_TAKEOFF = round(mean(delta_EGTHDM_TAKEOFF, na.rm = T),2),
                mean_cyc_loe_EGTHDM_TAKEOFF = round(mean(cyc_loe_EGTHDM_TAKEOFF, na.rm = T)),
                mean_hrs_loe_EGTHDM_TAKEOFF = round(mean(hrs_loe_EGTHDM_TAKEOFF, na.rm = T)),
                mean_days_loe_EGTHDM_TAKEOFF = round(mean(days_loe_EGTHDM_TAKEOFF, na.rm = T))
              )
          )
        )
      )

      df_g$ata_code <- row.names(df_g)
      
      row.names(df_g) <- NULL
      
      colnames(df_g) <- NULL
      
      DT::datatable({
        df_g
      },
      caption = "Summary",
      extensions = 'Buttons',
      options = list(
        dom = 'Bfrtip',
        buttons = list(
          list(
            extend = 'collection',
            buttons = c('csv', 'excel'),
            exportOptions = list(
              modifiers = list(page = "all")
            )
          )
        ),
        columnDefs=list(list(className='dt-center',targets="_all")
        ),
        scrollX = TRUE
      ),
      filter = "top",
      selection = 'single',
      class = 'hover', 
      rownames = FALSE
      )
    }
  })
  
  output$enginewash_summary_tablet <- renderTable({
    
    req(enginewash_data$df_event)
    
    if (is.null(enginewash_data$df_event)){
      return()
    }
    else{

      df_g <- as.data.frame(
        as.matrix(
          t(
            enginewash_data$df_event %>%
              group_by(ata_code) %>%
              summarise(
                count_washes = n(),
                count_engines = n_distinct(engine_id),
                mean_delta_GWFM_CRUISE = round(mean(delta_GWFM_CRUISE, na.rm = T),2),
                mean_cyc_loe_GWFM_CRUISE = round(mean(cyc_loe_GWFM_CRUISE, na.rm = T)),
                mean_hrs_loe_GWFM_CRUISE = round(mean(hrs_loe_GWFM_CRUISE, na.rm = T)),
                mean_days_loe_GWFM_CRUISE = round(mean(days_loe_GWFM_CRUISE, na.rm = T)),
                mean_delta_DEGT_CRUISE = round(mean(delta_DEGT_CRUISE, na.rm = T),2),
                mean_cyc_loe_DEGT_CRUISE = round(mean(cyc_loe_DEGT_CRUISE, na.rm = T)),
                mean_hrs_loe_DEGT_CRUISE = round(mean(hrs_loe_DEGT_CRUISE, na.rm = T)),
                mean_days_loe_DEGT_CRUISE = round(mean(days_loe_DEGT_CRUISE, na.rm = T)),
                mean_delta_EGTHDM_TAKEOFF = round(mean(delta_EGTHDM_TAKEOFF, na.rm = T),2),
                mean_cyc_loe_EGTHDM_TAKEOFF = round(mean(cyc_loe_EGTHDM_TAKEOFF, na.rm = T)),
                mean_hrs_loe_EGTHDM_TAKEOFF = round(mean(hrs_loe_EGTHDM_TAKEOFF, na.rm = T)),
                mean_days_loe_EGTHDM_TAKEOFF = round(mean(days_loe_EGTHDM_TAKEOFF, na.rm = T))
              )
          )
        )
      )
      
      df_g$ata_code <- row.names(df_g)
      
      row.names(df_g) <- NULL
      
      colnames(df_g) <- NULL
      
      df_g 
    }
  })
  
  output$enginewash_summary_plot <- renderPlot({
    
    req(input$enginewash_features_summary_pi)
    if(!is.null(enginewash_data$df_event) & !is.null(input$enginewash_features_summary_pi)){
      
      df_event <- enginewash_data$df_event
      browser()
      df_event$feature_to_plot <- df_event[[input$enginewash_features_summary_pi]]
      
      ggplot(
        data = df_event,
        aes(
          x = ata_code,
          y = feature_to_plot, #feature_to_plot,
          color = ata_code
        )
      ) + 
        geom_violin(alpha = 0.25) + 
        stat_summary(fun = "mean",
                     geom = "crossbar",
                     aes(color = ata_code)) +
        geom_jitter() +
        ggtitle(input$enginewash_features_summary_pi) +
        theme_minimal()
      #grid.arrange(p1,p2,p3,p4, ncol=2)
    }
    
  })
  
  observeEvent(
    input$update_enginewash_data,{
      if(
        any(
          is.null(input$enginewash_operator_pi),
          is.null(input$enginewash_actype_pi),
          is.null(input$enginewash_acreg_pi),
          is.null(input$dri_enginewash_date),
          is.null(input$pi_enginewash_atacode)
          #,is.null(input$enginewash_parameters_takeoff_pi)
        )
      ){
        
        showModal(
          modalDialog(
            fluidPage(
              h3("Please select all elements of header")
            ),
            easyClose = TRUE
          )
        )
        
      }
      else{
        
        # calchist <- CalculatorHistory$new()
        # 
        # calchist$process_history(
        #   operator = input$enginewash_operator_pi, #"s7",
        #   aircraft_type = input$enginewash_actype_pi,#"B737-800",
        #   min_flight_datetime = input$dri_enginewash_date[1],
        #   max_flight_datetime = input$dri_enginewash_date[2],
        #   ata_code = input$pi_enginewash_atacode, #c("206","207","209"),
        #   flight_phase = "TAKEOFF",
        #   parameter_name = input$enginewash_parameters_takeoff_pi #"EGTHDM"
        # )
        # 
        # enginewash_data$df <- calchist$df
        # enginewash_data$df_event <- calchist$df_event
        
        
        calchist <- CalculatorHistory_v2$new()
        
        params <- data.frame(
          parameter_name = c("GWFM","DEGT","EGTHDM"),
          flight_phase = c("CRUISE","CRUISE","TAKEOFF"),
          smooth_window = c(30,30,30),
          number_of_obs_mean = c(15,15,15),
          threshhold = c(0.05,2,2),
          cartoonist = c(-1,-1,1)
        )
        
        list_calchist_df <- list()
        list_calchist_df_event <- list()
        
        for(i in 1:nrow(params)){
          
          calchist$process_history(
            operator = input$enginewash_operator_pi, #"s7",
            aircraft_type = input$enginewash_actype_pi,#"B737-800",
            min_flight_datetime = input$dri_enginewash_date[1],
            max_flight_datetime = input$dri_enginewash_date[2],
            ata_code = input$pi_enginewash_atacode, # c("206","207","209"),
            flight_phase = params$flight_phase[i],
            parameter_name = params$parameter_name[i],  #"GWFM", # "DEGT",
            smooth_window = params$smooth_window[i],
            number_of_obs_mean = params$number_of_obs_mean[i],
            threshhold = params$threshhold[i],
            cartoonist = params$cartoonist[i]
          )
          
          list_calchist_df[[as.character(i)]] <- calchist$df
          list_calchist_df[[as.character(i)]]$parameter_name <- params$parameter_name[i]
          
          df_event <- calchist$df_event[,c(
            "ac_reg_new",
            "engine_position",
            "engine_id",
            "maint_datetime",
            "ata_code",
            "delta_float_value_custom",
            "mean_float_value_custom_before_wash",
            "mean_float_value_custom_after_wash",
            "time_loss_of_efficiency",
            # "departures",
            # "arrivals",
            # "flights",
            "cyc_loss_off_efficiency",
            "hrs_loss_off_efficiency"
          )]
          
          df_event <- df_event[!duplicated(df_event),]
          df_event <- df_event[!is.na(df_event$delta_float_value_custom),]
          df_event$maint_datetime <- as.Date(df_event$maint_datetime)
          df_event$time_loss_of_efficiency <- as.Date(df_event$time_loss_of_efficiency)
          df_event$days_loss_of_efficiency <- as.numeric(df_event$time_loss_of_efficiency - df_event$maint_datetime)
          
          for(col in c("delta_float_value_custom",
                       "mean_float_value_custom_before_wash",
                       "mean_float_value_custom_after_wash",
                       "hrs_loss_off_efficiency")){
            df_event[,col] <- round(df_event[,col],2)
            
          }
          
          colnames(df_event)[
            colnames(df_event) == "delta_float_value_custom"
            ] <- paste0(
              "delta_",
              params$parameter_name[i],
              "_",
              params$flight_phase[i]
            )
          
          colnames(df_event)[
            colnames(df_event) == "mean_float_value_custom_before_wash"
            ] <- paste0(
              "mean_",
              params$parameter_name[i],
              "_",
              params$flight_phase[i],
              "_before_wash"
            )
          
          colnames(df_event)[
            colnames(df_event) == "mean_float_value_custom_after_wash"
            ] <- paste0(
              "mean_",
              params$parameter_name[i],
              "_",
              params$flight_phase[i],
              "_after_wash"
            )
          
          colnames(df_event)[
            colnames(df_event) == "time_loss_of_efficiency"
            ] <- paste0(
              "date_loe_",
              params$parameter_name[i],
              "_",
              params$flight_phase[i]
            )
          
          colnames(df_event)[
            colnames(df_event) == "cyc_loss_off_efficiency"
            ] <- paste0(
              "cyc_loe_",
              params$parameter_name[i],
              "_",
              params$flight_phase[i]
            )
          
          colnames(df_event)[
            colnames(df_event) == "hrs_loss_off_efficiency"
            ] <- paste0(
              "hrs_loe_",
              params$parameter_name[i],
              "_",
              params$flight_phase[i]
            )
          
          colnames(df_event)[
            colnames(df_event) == "days_loss_of_efficiency"
            ] <- paste0(
              "days_loe_",
              params$parameter_name[i],
              "_",
              params$flight_phase[i]
            )
          
          list_calchist_df_event[[as.character(i)]] <- df_event
          
        }
        
        enginewash_data$list_calchist_df <- list_calchist_df
        # browser()
        enginewash_data$df_event <- list_calchist_df_event[[as.character(3)]] %>%
          left_join(
            list_calchist_df_event[[as.character(2)]],
            by = c(
              "ac_reg_new" = "ac_reg_new",
              "engine_position" = "engine_position",
              "engine_id" = "engine_id",
              "maint_datetime" = "maint_datetime",
              "ata_code" = "ata_code"
            )
          )%>%
          left_join(
            list_calchist_df_event[[as.character(1)]],
            by = c(
              "ac_reg_new" = "ac_reg_new",
              "engine_position" = "engine_position",
              "engine_id" = "engine_id",
              "maint_datetime" = "maint_datetime",
              "ata_code" = "ata_code"
            )
          )
        
      }
    })
  
  observeEvent(input$ab_show_summary,{
    showModal(modal_save_report)
  })
  # 
  # 
  modal_save_report <- modalDialog(
    fluidPage(
      h3("Summary"),
      withSpinner(tableOutput(ns("enginewash_summary_tablet"))),
      pickerInput(
        ns("enginewash_features_summary_pi"),
        label = "Features",
        choices = c(
          "delta_EGTHDM_TAKEOFF",
          "delta_DEGT_CRUISE",
          "delta_GWFM_CRUISE",
          "cyc_loe_EGTHDM_TAKEOFF",
          "cyc_loe_DEGT_CRUISE",
          "cyc_loe_GWFM_CRUISE",
          "hrs_loe_EGTHDM_TAKEOFF",
          "hrs_loe_DEGT_CRUISE",
          "hrs_loe_GWFM_CRUISE",
          "days_loe_EGTHDM_TAKEOFF",
          "days_loe_DEGT_CRUISE",
          "days_loe_GWFM_CRUISE"
        ),
        selected = "delta_EGTHDM_TAKEOFF",
        multiple = F
      ),
      withSpinner(plotOutput(ns("enginewash_summary_plot"), height = '700px'))
    ),
    size="xl"
  )
  
  
  output$enginewash_workspace <- renderUI({
    
    fluidRow(
      bs4Card(
        width = 12,
        headerBorder = FALSE,
        collapsible = FALSE,
        fluidRow(
          column(
            4,
            fluidRow(
              column(
                4,
                uiOutput(ns("enginewash_operator"))
              ),
              column(
                4,
                uiOutput(ns("enginewash_actype"))
              ),
              column(
                4,
                uiOutput(ns("enginewash_acreg"))
              )
            )
            
          ),
          column(1),
          column(
            7,
            fluidRow(
              column(
                3,
                uiOutput(ns("enginewash_atacode"))
              ),
              column(
                3,
                dateRangeInput(
                  ns("dri_enginewash_date"),
                  "Date range:",
                  start = '2022-10-01',
                  end = '2023-06-01'
                )
              ),
              column(
                3
                #,uiOutput(ns("enginewash_parameter_takeoff"))
              ),
              column(
                3,
                hr(),
                actionBttn(ns("update_enginewash_data"), "Calculate")
              )
            )
          )
        )
      ),
      
      bs4Card(
        width = 6,
        headerBorder = FALSE,
        collapsible = FALSE,
        withSpinner(DT::dataTableOutput(ns("enginewash_details_table"))),
        hr(),
        actionBttn(ns("ab_show_summary"), "Show summary")
        # withSpinner(DT::dataTableOutput(ns("enginewash_summary_table")))
        # withSpinner(tableOutput(ns("enginewash_summary_tablet")))
      ),
      bs4Card(
        width = 6,
        headerBorder = FALSE,
        collapsible = FALSE,
        div(
          style = 'overflow-y:scroll;height:750px;',
          withSpinner(htmlOutput(ns("enginewash_details_plot_hc")))
        )
      )
      
    )
    
  })
  
}