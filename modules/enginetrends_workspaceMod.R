enginetrends_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("enginetrends_workspace"))
  
}

enginetrends_workspaceMod <- function(input, output, session, credentials, pool) {
  
  ns <- session$ns
  
  output$enginetrends_operator <- renderUI({
    
    ns <- session$ns
    
    fleetsummary <- pool %>% tbl(in_schema("ecmapp", "_fleetsummary")) %>% collect()
    
    userdefault_test <- pool %>%
      tbl(in_schema("utair", "userdefault_test")) %>%
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      selected <- unique(fleetsummary$operator)[1]
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi
      
    }
    
    pickerInput(
      ns("enginetrends_operator_pi"),
      label = "Operator",
      choices = unique(fleetsummary$operator), # "utair",
      options = list(
        `live-search`=TRUE,
        `actions-box` = TRUE,
        `deselect-all-text` = "deselect",
        `select-all-text` = "select all",
        `none-selected-text` = "zero"
      ),
      selected =  selected, #"utair",
      multiple = F
    )  
    
  })
  
  output$enginetrends_actype <- renderUI({
    
    ns <- session$ns
    
    choices <- NULL
    
    choicesOpt <- NULL
    # browser()
    selected <- NULL
    
    df_choices <- NULL
    
    if(!is.null(input$enginetrends_operator_pi)){
      
      df_choices <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$enginetrends_operator_pi
        ) %>%
        group_by(
          operator,
          aircraft_type
        ) %>%
        summarise(
          count_ac = n_distinct(aircraft_id)
        ) %>%
        collect()
      
      userdefault_test <- pool %>% 
        tbl(in_schema("utair", "userdefault_test")) %>% 
        filter(
          user %in% !!credentials()$user
        ) %>%
        collect()
      
      if(
        nrow(userdefault_test) == 0 |
        jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi != input$enginetrends_operator_pi
      ){
        
        selected <- choices$aircraft_type[1]
        
      }
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_actype_pi
        
      }
      
      df_choices <- df_choices[!(df_choices$aircraft_type %in% c("ERJ175", "A330-200")),] #,"B777-300ER"
      
      choices <- lapply(split(df_choices$aircraft_type, df_choices$operator), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(df_choices$count_ac, df_choices$operator), as.list))
      )
      
    }
    # browser()

    
    pickerInput(
      ns("enginetrends_actype_pi"),
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
      selected = df_choices$aircraft_type, # selected,#"ATR72-212",
      multiple = T
    )
    
  })
  
  output$enginetrends_acreg <- renderUI({
    
    ns <- session$ns
    
    choices <- NULL
    
    choicesOpt <- NULL
    
    selected <- NULL
    
    multiple <- TRUE

    if(!is.null(input$enginetrends_actype_pi) & !is.null(input$enginetrends_operator_pi) & !is.null(input$enginetrends_acreg_multiple)){
      # browser()
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$enginetrends_operator_pi,
          aircraft_type %in% !!input$enginetrends_actype_pi,
          #is.na(removal_datetime),
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
        
        #}
        
        # browser()
        
        userdefault_test <- pool %>% 
          tbl(in_schema("utair", "userdefault_test")) %>% 
          filter(
            user %in% !!credentials()$user
          ) %>%
          collect()
        
        if(
          nrow(userdefault_test) == 0 |
          jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi != input$enginetrends_operator_pi
        ){
          
          selected <- df_choices$ac_reg_new[1]
          
        }
        else{
          
          selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_acreg_pi
          
        }
        
        multiple <- input$enginetrends_acreg_multiple
        
        # }
        
      }

    }
    
    pickerInput(
      ns("enginetrends_acreg_pi"),
      label = "A/C Reg:", 
      choices = choices,
      choicesOpt = choicesOpt, 
      options = list(
        `live-search`=TRUE,
        `dropdown-align-right` = TRUE
      ),
      selected = selected,
      multiple = multiple
    )
    
  })
  
  output$enginetrends_presetname <- renderUI({
    
    ns <- session$ns
    
    choices <- NULL
    
    choicesOpt <- NULL
    
    selected <- NULL
    
    #req(input$enginetrends_actype_pi, input$enginetrends_operator_pi)
    if(!is.null(input$enginetrends_operator_pi)){
      
      preset <- pool %>%
        tbl(in_schema("ecmapp", "preset")) %>%
        filter(
          aircraft_family %in% c(
            !!input$enginetrends_actype_pi,
            "ALL"
          ) &
            operator %in% !!input$enginetrends_operator_pi # OPERATOR IN SELECTED PRESET NAME !!!!!!!!!!!!!!!!!!!!!
        ) %>%
        group_by(
          report_name,
          report_family
        ) %>%
        summarise(
          count_params = n_distinct(main_param_name)
        ) %>%
        mutate(
          subtext = paste(count_params, "params")
        ) %>%
        collect()
      #browser()
      
      # preset <- preset[order(match(preset$report_family, c("MAIN","SPECIALIZED", "CUSTOM"))),]
      
      choices <- lapply(split(preset$report_name, preset$report_family), as.list)
      
      choicesOpt <- list(
        subtext = unlist(lapply(split(preset$subtext, preset$report_family), as.list))
      )
      
      choices <- choices[order(match(names(choices), c("MAIN","SPECIALIZED", "CUSTOM")))]
      
      choicesOpt <- choicesOpt[order(match(names(choicesOpt), c("MAIN","SPECIALIZED", "CUSTOM")))]
      
      userdefault_test <- pool %>% 
        tbl(in_schema("utair", "userdefault_test")) %>% 
        filter(
          user %in% !!credentials()$user
        ) %>%
        collect()
      
      if(
        nrow(userdefault_test) == 0 |
        jsonlite::fromJSON(userdefault_test$default)$enginetrends_operator_pi != input$enginetrends_operator_pi
      ){
        
        # selected <- c("TAKE OFF trends (MAIN)")
        # browser()
        selected <- preset$report_name[1]
        
      }
      else{
        
        selected <- jsonlite::fromJSON(userdefault_test$default)$enginetrends_presetname_pi
        
      }
      
    }
    
    pickerInput(
      ns("enginetrends_presetname_pi"),
      label = "Preset",
      choices = choices, 
      choicesOpt = choicesOpt,
      selected = selected,
      options = list(
        `live-search`=TRUE
      ),
      multiple = F
    )
    
  })
  
  output$enginetrends_plotoptions <- renderUI({
    
    ns <- session$ns
    
    userdefault_test <- pool %>% 
      tbl(in_schema("utair", "userdefault_test")) %>% 
      filter(
        user %in% !!credentials()$user
      ) %>%
      collect()
    
    if(nrow(userdefault_test) == 0){
      
      selected <- NULL
      
    }
    else{
      
      selected <- jsonlite::fromJSON(userdefault_test$default)
      
    }
    
    dropdownButton(
      
      inputId = "mydropdown",
      label = "Plot options",
      icon = icon("gear"),
      status = "default",
      circle = FALSE,
      tooltip = tooltipOptions(title = "Click to see options !"),
      accordion(
        id = "plotoptionsaccotdion",
        
        accordionItem(
          id = "accordion_item_m1",
          title = "Multiple A/C selection",
          status = "warning",
          collapsed = FALSE,
          
          checkboxInput(ns("enginetrends_acreg_multiple"), "Enable multiple selection", FALSE)
        ),
        
        
        accordionItem(
          id = "accordion_item_0",
          title = "Position",
          status = "warning",
          collapsed = FALSE,
          
          radioButtons(
            ns("rb_engine_position"), 
            label = NULL,
            choices = list(
              "All" = 1,
              "Engine pos. 1" = 2,
              "Engine pos. 2" = 3
            ), 
            selected = as.numeric(selected$rb_engine_position)
          )
        ),
        
        accordionItem(
          id = "accordion_item_1",
          title = "Smooth",
          status = "warning",
          collapsed = FALSE,
          
          radioButtons(
            ns("rb_enable_smooth"), 
            label = NULL,
            choices = list(
              "Only smooth" = 1,
              "Only raw" = 2,
              "Smooth and raw" = 3
            ), 
            #selected = 3
            selected = as.numeric(selected$rb_enable_smooth)
          ),
          numericInput(
            ns("smooth_window"),
            label = NULL,
            as.numeric(selected$smooth_window), 
            min = 1, 
            max = 100
          )
        ),
        accordionItem(
          id = "accordion_item_3",
          title = "Alerts/Maintenance",
          status = "warning",
          collapsed = FALSE,
          checkboxGroupInput(
            ns("cgi_show_alerts"),
            label = NULL,
            choices = c(
              "Show alerts",
              "Show maintenance actions",
              "Show previous installations"
            ),
            selected = selected$cgi_show_alerts,
            inline = FALSE
          )
        ),
        accordionItem(
          id = "accordion_item_4",
          title = "Graph size/range",
          status = "warning",
          collapsed = FALSE,
          radioGroupButtons(
            ns("rb_graph_size"),
            label = NULL,
            size = "sm",
            status = "warning",
            choices = c(
              `<i class='fa fa-th-large'></i>` = "multiple", 
              `<i class='fa fa-th-list'></i>` = "line", 
              `<i class='fa fa-stop'></i>` = "one"
            ),
            selected = selected$rb_graph_size,
            justified = FALSE
          ),
          radioButtons(
            ns("rb_range_selector"), 
            label = NULL,
            choices = list(
              "1m",
              "3m",
              "6m",
              "YTD",
              "1y",
              "ALL"
            ), 
            selected = selected$rb_range_selector
          )
        ),
        accordionItem(
          id = "accordion_item_5",
          title = "Show baseline",
          status = "warning",
          collapsed = FALSE,
          
          checkboxInput(ns("ci_baseline"), "Show baseline", TRUE)
        )
      )
    )
    
  })
  
  observeEvent(input$ab_prev,{
    if(!is.null(input$enginetrends_acreg_pi)){
      
      selected <- NULL
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$enginetrends_operator_pi,
          aircraft_type %in% !!input$enginetrends_actype_pi,
          #is.na(removal_datetime),
          ac_reg_new != "-"
        ) %>%
        collect()
      
      fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
      
      # browser()
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
      
      
      if(df_choices$ac_reg_new[min(which(df_choices$ac_reg_new %in% input$enginetrends_acreg_pi))] == df_choices$ac_reg_new[1]){
        
        showModal(
          modalDialog(
            fluidPage(
              h3("This was the first aircraft on the list")
            ),
            easyClose = TRUE
          )
        )
        
        selected <- df_choices$ac_reg_new[length(df_choices$ac_reg_new)]
        
      }
      else{
        
        selected <- df_choices$ac_reg_new[min(which(df_choices$ac_reg_new %in% input$enginetrends_acreg_pi)) - 1]
        
      }
      
      enginetrends_data$enginetrends_acreg_pi <- selected
      
      updatePickerInput(
        session = session,
        inputId = "enginetrends_acreg_pi",
        label = "A/C Reg:",
        # choices = choices_list,
        # choicesOpt = list(
        #   subtext = choices_old_vec
        # ), 
        selected = selected,
        options = list(
          #`actions-box` = TRUE,
          `live-search`=TRUE
        )
      ) 
      
    }}, priority = 2)
  
  observeEvent(input$ab_next,{
    
    if(!is.null(input$enginetrends_acreg_pi)){
      
      # browser()
      
      selected <- NULL
      
      fleetsummary <- pool %>%
        tbl(in_schema("ecmapp", "_fleetsummary")) %>%
        filter(
          operator %in% !!input$enginetrends_operator_pi,
          aircraft_type %in% !!input$enginetrends_actype_pi,
          #is.na(removal_datetime),
          ac_reg_new != "-"
        ) %>%
        collect()
      
      fleetsummary <- fleetsummary[!duplicated(fleetsummary),]
      
      
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
      
      
      if(df_choices$ac_reg_new[max(which(df_choices$ac_reg_new %in% input$enginetrends_acreg_pi))] == df_choices$ac_reg_new[length(df_choices$ac_reg_new)]){
        
        showModal(
          modalDialog(
            fluidPage(
              h3("This was the last aircraft on the list")
            ),
            easyClose = TRUE
          )
        )
        
        selected <- df_choices$ac_reg_new[1]
        
      }
      else{
        
        selected <- df_choices$ac_reg_new[max(which(df_choices$ac_reg_new %in% input$enginetrends_acreg_pi)) + 1]
        
      }
      
      enginetrends_data$enginetrends_acreg_pi <- selected
      
      updatePickerInput(
        session = session,
        inputId = "enginetrends_acreg_pi",
        label = "A/C Reg:",
        # choices = choices_list,
        # choicesOpt = list(
        #   subtext = choices_old_vec
        # ), 
        selected = selected,
        options = list(
          #`actions-box` = TRUE,
          `live-search`=TRUE
        )
      ) 
      
    }
    
  }, priority = 2)
  
  observeEvent(
    input$update_enginetrends_data,{
      if(
        any(
          is.null(input$enginetrends_operator_pi),
          is.null(input$enginetrends_actype_pi),
          is.null(input$enginetrends_acreg_pi),
          is.null(input$enginetrends_presetname_pi),
          is.null(input$rb_enable_smooth),
          is.null(input$smooth_window),
          #is.null(input$cgi_show_alerts),
          is.null(input$rb_graph_size),
          is.null(input$rb_range_selector),
          is.null(input$rb_engine_position),
          is.null(input$ci_baseline)
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
        enginetrends_data$enginetrends_acreg_pi <- input$enginetrends_acreg_pi
      }
    },
    priority = 200
  )
  
  enginetrends_data <- reactiveValues(
    fleetsummary = NULL,
    preset = NULL,
    params = NULL,
    params_aircraft = NULL,
    alerts = NULL,
    alert_code = NULL,
    atacode = NULL,
    maintenance = NULL,
    atacodecolor = NULL,
    config = NULL,
    enginetrends_acreg_pi = NULL
  )
  
  observeEvent(
    list(
      input$update_enginetrends_data,
      input$ab_prev,
      input$ab_next
    ),{
    
    req(
      input$update_enginetrends_data != 0 |
        input$ab_prev != 0 |
        input$ab_next != 0
    )
      
    # browser()
    if(
      any(
        is.null(input$enginetrends_operator_pi),
        is.null(input$enginetrends_actype_pi),
        is.null(input$enginetrends_acreg_pi),
        is.null(input$enginetrends_presetname_pi),
        is.null(input$rb_enable_smooth),
        is.null(input$smooth_window),
        #is.null(input$cgi_show_alerts),
        is.null(input$rb_graph_size),
        is.null(input$rb_range_selector),
        is.null(input$rb_engine_position),
        is.null(input$ci_baseline)
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
      
      if(!is.null(input$rb_range_selector)){
        
        if(input$rb_range_selector == "1m"){
          
          mintime <- Sys.Date() - 30
          
        }
        else if(input$rb_range_selector == "3m"){
          
          mintime <- Sys.Date() - 90
          
        }
        else if(input$rb_range_selector == "6m"){
          
          mintime <- Sys.Date() - 180
          
        }
        else if(input$rb_range_selector == "1y"){
          
          mintime <- Sys.Date() - 360
          
        }
        else if(input$rb_range_selector == "1y"){
          
          mintime <- Sys.Date() - 360
          
        }
        
        else if(input$rb_range_selector == "YTD"){
          
          mintime <- Sys.Date() - 360
          
        }
        
        else if(input$rb_range_selector == "ALL"){
          
          mintime <- as.Date('2010-01-01')
          
        }
        
        enginetrends_data$fleetsummary <- pool %>%
          tbl(in_schema("ecmapp", "_fleetsummary")) %>%
          filter(
            ac_reg_new %in% !! enginetrends_data$enginetrends_acreg_pi & 
              (removal_datetime >= !!mintime | is.na(removal_datetime))
          ) %>%
          collect()
        
        enginetrends_data$fleetsummary <- enginetrends_data$fleetsummary[!duplicated(enginetrends_data$fleetsummary),]
        
        enginetrends_data$preset <- pool %>%
          tbl(in_schema("ecmapp", "preset")) %>%
          filter(
            report_name == !!input$enginetrends_presetname_pi & 
              operator %in% !!input$enginetrends_operator_pi &
              !is.na(report_name) &
              !is.na(report_name) & 
              !is.na(main_param_name) & 
              !is.na(main_flght_phs)
          ) %>%
          group_by(
            report_name,
            main_param_name,
            main_flght_phs,
            table_name,
            alias,
            param_description,
            item_type,
            id_sort
          ) %>%
          summarise(
            count_params = n()
          ) %>%
          collect()
        
        enginetrends_data$params <- pool %>%
          tbl(in_schema("ecmapp", "engine_raw_output_mv")) %>%
          mutate(
            parameter_name_flight_phase = paste0(
              parameter_name,
              "_",
              flight_phase
            )
          ) %>%
          filter(
            aircraft_id %in% !!unique(enginetrends_data$fleetsummary$aircraft_id) &
              parameter_name_flight_phase %in% !!unique(
                paste0(
                  enginetrends_data$preset$main_param_name,
                  "_",
                  enginetrends_data$preset$main_flght_phs
                )
              ) & 
              flight_datetime >= !!mintime
              
          ) %>%
          collect()
        
        # if(unique(enginetrends_data$fleetsummary$aircraft_family) %in% c("A320 NEO","A321 NEO")){
        #   
        #   schm <- "s7_neo"
        #   
        # }
        # else{
        #   
        #   schm <- "ecmapp"
        #   
        # }
        
        enginetrends_data$params <- rbind(
          enginetrends_data$params,
          pool %>%
            tbl(in_schema("ecmapp", "engine_input_mv")) %>%
            mutate(
              parameter_name_flight_phase = paste0(
                parameter_name,
                "_",
                flight_phase
              )
            ) %>%
            filter(
              aircraft_id %in% !!unique(enginetrends_data$fleetsummary$aircraft_id) &
                parameter_name_flight_phase %in% !!unique(
                  paste0(
                    enginetrends_data$preset$main_param_name,
                    "_",
                    enginetrends_data$preset$main_flght_phs
                  )
                ) & 
                flight_datetime >= !!mintime
            ) %>%
            collect()
        )
        
        # enginetrends_data$params <- enginetrends_data$params[,setdiff(
        #   colnames(enginetrends_data$params),
        #   c(
        #     "integer_value",
        #     "char_value"
        #   )
        # )]
        
        flightinfo_input <- pool %>%
          tbl(in_schema("ecmapp", "flightinfo_input_mv")) %>%
          mutate(
            parameter_name_flight_phase = paste0(
              parameter_name,
              "_",
              flight_phase
            )
          ) %>%
          filter(
            aircraft_id %in% !!unique(enginetrends_data$fleetsummary$aircraft_id) &
              parameter_name_flight_phase %in% !!unique(
                paste0(
                  enginetrends_data$preset$main_param_name,
                  "_",
                  enginetrends_data$preset$main_flght_phs
                )
              ) & 
              flight_datetime >= !!mintime
          ) %>%
          collect()
        
        flightinfo_input$integer_value <- NA
        
        flightinfo_input$char_value <- NA
        
        enginetrends_data$params <- rbind(
          enginetrends_data$params,
          flightinfo_input
          
        )
        
        enginetrends_data$params$float_value[
          !is.na(enginetrends_data$params$integer_value)
        ] <- enginetrends_data$params$integer_value[
          !is.na(enginetrends_data$params$integer_value)
          ]
        
        aircraft <- pool %>%
          tbl(in_schema("ecmapp", "aircraft")) %>%
          filter(
            aircraft_id %in% !!unique(enginetrends_data$fleetsummary$aircraft_id)
          ) %>%
          collect()
        
        aircraft_names <- pool %>%
          tbl(in_schema("ecmapp", "aircraft_names")) %>%
          filter(
            ac_serial %in% !!unique(enginetrends_data$fleetsummary$aircraft_id)
          ) %>%
          collect()
        
        # browser()
        # engine_config <- pool %>%
        #   tbl(in_schema("ecmapp", "engine_config")) %>%
        #   filter(
        #     engine_id %in% !!unique(enginetrends_data$fleetsummary$engine_id)
        #   ) %>%
        #   collect()
        
        engine_config <- pool %>%
          tbl(in_schema("ecmapp", "_engine_config")) %>%
          filter(
            engine_id %in% !!unique(enginetrends_data$fleetsummary$engine_id)
          ) %>%
          collect()
        
        
        engine_config <- engine_config %>% 
          group_by(engine_id) %>% 
          slice_max(change_date)
        
        engine_config <- engine_config[!duplicated(engine_config$engine_id),c("engine_id","n1_modifier")]
        
        enginetrends_data$fleetsummary <- enginetrends_data$fleetsummary %>%
          left_join(
            engine_config,
            by = c(
              "engine_id" = "engine_id"
            )
          )
        
        enginetrends_data$params <- enginetrends_data$params %>%
          left_join(
            engine_config,
            by = c(
              "engine_id" = "engine_id"
            )
          )
        
        enginetrends_data$params <- enginetrends_data$params %>%
          left_join(
            aircraft_names,
            by = c(
              "aircraft_id" = "ac_serial"
            )
          )
        
        enginetrends_data$params <- enginetrends_data$params %>%
          left_join(
            aircraft,
            by = c(
              "aircraft_id" = "aircraft_id"
            )
          )
        
        enginetrends_data$params_aircraft <- pool %>%
          tbl(in_schema("ecmapp", "aircraft_input_mv")) %>%
          filter(
            aircraft_id %in% !!unique(enginetrends_data$fleetsummary$aircraft_id) &
              flight_phase %in% !!enginetrends_data$preset$main_flght_phs &
              parameter_name %in% !!enginetrends_data$preset$main_param_name & 
              flight_datetime >= !!mintime
          ) %>%
          collect()
        
        enginetrends_data$params_aircraft <- rbind(
          enginetrends_data$params_aircraft,
          pool %>%
            tbl(in_schema("ecmapp", "aircraft_raw_outpt_mv")) %>%
            filter(
              aircraft_id %in% !!unique(enginetrends_data$fleetsummary$aircraft_id) &
                flight_phase %in% !!enginetrends_data$preset$main_flght_phs &
                parameter_name %in% !!enginetrends_data$preset$main_param_name & 
                flight_datetime >= !!mintime
            ) %>%
            collect()
        )
        
        enginetrends_data$params_aircraft$float_value[
          !is.na(enginetrends_data$params_aircraft$integer_value)
          ] <- enginetrends_data$params_aircraft$integer_value[
            !is.na(enginetrends_data$params_aircraft$integer_value)
            ]
        
        enginetrends_data$params_aircraft <- enginetrends_data$params_aircraft %>%
          left_join(
            aircraft_names,
            by = c(
              "aircraft_id" = "ac_serial"
            )
          )
        
        enginetrends_data$params_aircraft <- enginetrends_data$params_aircraft %>%
          left_join(
            aircraft,
            by = c(
              "aircraft_id" = "aircraft_id"
            )
          )
        
        enginetrends_data$alerts <- pool %>%
          tbl(in_schema("ecmapp", "alert_output")) %>%
          filter(
            aircraft_id %in% !!unique(enginetrends_data$fleetsummary$aircraft_id) &
              flight_phase %in% !!enginetrends_data$preset$main_flght_phs &
              parameter_name %in% !!enginetrends_data$preset$main_param_name & 
              flight_datetime >= !!mintime
          ) %>%
          collect()
        
        
        enginetrends_data$alert_code <- pool %>%
          tbl(in_schema("s7_mdb", "alert_code")) %>%
          collect()

        enginetrends_data$maintenance <- pool %>%
          tbl(in_schema("ecmapp", "maintenance")) %>%
          filter(
            engine_id %in% !!unique(enginetrends_data$fleetsummary$engine_id) & 
              maint_datetime >= !!mintime
          ) %>%
          collect()
        
        enginetrends_data$atacodecolor <- pool %>%
          tbl(in_schema("ecmapp", "atacodecolor_operator")) %>%
          filter(
            operator %in% !!input$enginetrends_operator_pi,
            ata_code %in% !!unique(enginetrends_data$maintenance$ata_code)
          ) %>%
          collect()
        
        enginetrends_data$maintenance <- enginetrends_data$maintenance %>% 
          left_join(
            enginetrends_data$atacodecolor,
            by = c("ata_code" = "ata_code")
          )

        enginetrends_data$maintenance <- enginetrends_data$maintenance[
          !duplicated(enginetrends_data$maintenance[,c("engine_id","maint_datetime","ata_code","reason")])
          ,]
        
        if(input$rb_range_selector == "1m"){
          
          enginetrends_data$range_selector <- 0
          
        }
        else if(input$rb_range_selector == "3m"){
          
          enginetrends_data$range_selector <- 1
          
        }
        else if(input$rb_range_selector == "6m"){
          
          enginetrends_data$range_selector <- 2
          
        }
        else if(input$rb_range_selector == "YTD"){
          
          enginetrends_data$range_selector <- 3
          
        }
        else if(input$rb_range_selector == "1y"){
          
          enginetrends_data$range_selector <- 4
          
        }
        else if(input$rb_range_selector == "ALL"){
          
          enginetrends_data$range_selector <- 5
          
        }
        
        if(input$rb_engine_position == "1"){
          
          rb_engine_position <- 0
          
        }
        else if(input$rb_engine_position == "2"){
          
          rb_engine_position <- 1
          
        }
        else if(input$rb_engine_position == "3"){
          
          rb_engine_position <- 2
          
        }
        
        if(rb_engine_position != 0){
          
          enginetrends_data$params <- enginetrends_data$params[enginetrends_data$params$engine_position == rb_engine_position,]
          
          enginetrends_data$alerts <- enginetrends_data$alerts[enginetrends_data$alerts$engine_position == rb_engine_position,]
          
          enginetrends_data$fleetsummary <- enginetrends_data$fleetsummary[enginetrends_data$fleetsummary$engine_position == rb_engine_position,]
          
        }
        
        if(!("Show previous installations" %in% input$cgi_show_alerts)){
          
          # enginetrends_data$params <- enginetrends_data$params[
          #   !(enginetrends_data$params$engine_id %in% unique(
          #     enginetrends_data$fleetsummary$engine_id[!is.na(
          #       enginetrends_data$fleetsummary$removal_datetime
          #     )])),
          #   ]
          enginetrends_data$params <- enginetrends_data$params[
            enginetrends_data$params$engine_id %in% unique(
              enginetrends_data$fleetsummary$engine_id[is.na(
                enginetrends_data$fleetsummary$removal_datetime
              )]
            ),
            ]
          
          enginetrends_data$fleetsummary <- enginetrends_data$fleetsummary[is.na(
            enginetrends_data$fleetsummary$removal_datetime
          ),]
          
        }
        # browser()
        
        if(
          length(unique(enginetrends_data$fleetsummary$aircraft_id)) == 1 & 
          length(unique(enginetrends_data$fleetsummary$engine_id)) == 2
        ){
          
          #1 color_raw <- "#7cb5ec70" color_raw_line <- "#7cb5ec20" 2 color_raw <- "#ff824370" color_raw_line <- "#ff824320"
          
          enginetrends_data$color_engine <- data.frame(
            engine_id = unique(c(
              enginetrends_data$fleetsummary$engine_id[
                enginetrends_data$fleetsummary$engine_position == 1
              ],
              enginetrends_data$fleetsummary$engine_id[
                enginetrends_data$fleetsummary$engine_position == 2
                ]
            )),
            colors_raw = c("#7cb5ec85", "#ff824385"),
            colors_smooth = c("#7cb5ec", "#ff8243"),
            status = c("info", "orange"),
            stringsAsFactors = FALSE
          )
          
        }
        else{
          colors_smooth <- c("#007bff", "#17a2b8", "#28a745", "#ffc107", "#dc3545", "#f012be")
          
          colors_raw <- paste0(
            colors_smooth,
            "70"
          )
          
          status <- c("primary", "info", "success", "warning", "danger", "fuchsia")
          
          colors_smooth <- rep(colors_smooth, length.out = length(unique(enginetrends_data$fleetsummary$engine_id)))
          
          colors_raw <- rep(colors_raw, length.out = length(unique(enginetrends_data$fleetsummary$engine_id)))
          
          status <- rep(status, length.out = length(unique(enginetrends_data$fleetsummary$engine_id)))
          
          vec_engine_id <- stringr::str_sort(unique(enginetrends_data$fleetsummary$engine_id), decreasing = FALSE, numeric = TRUE)
          
          enginetrends_data$color_engine <- data.frame(
            colors_raw = colors_raw,
            colors_smooth = colors_smooth,
            engine_id = vec_engine_id,
            status = status,
            stringsAsFactors = FALSE
          )
        }

        
        enginetrends_data$rb_enable_smooth = input$rb_enable_smooth
        enginetrends_data$cgi_show_alerts = input$cgi_show_alerts
        enginetrends_data$smooth_window = input$smooth_window
        enginetrends_data$rb_graph_size = input$rb_graph_size
        enginetrends_data$ci_baseline = input$ci_baseline
        #enginetrends_data$rb_engine_position = headerselectors$plotoptions$rb_engine_position()
        # browser()
      } 
      
    }
    
  }, priority = 0)
  
  output$enginetrends_preset <- renderUI({
    
    req(enginetrends_data$preset)
    
    if (is.null(enginetrends_data$preset)){
      # h3(
      #   "Please press Update plots"
      # )
      return()
    }
    else{
      enginetrendsVisualization(
        fleetsummary = enginetrends_data$fleetsummary,
        preset = enginetrends_data$preset,
        params = enginetrends_data$params,
        paramssmooth = NULL,
        params_aircraft = enginetrends_data$params_aircraft,
        alerts = enginetrends_data$alerts,
        alert_code = enginetrends_data$alert_code,
        maintenance = enginetrends_data$maintenance,
        range_selector = enginetrends_data$range_selector,
        rb_enable_smooth = enginetrends_data$rb_enable_smooth,
        cgi_show_alerts = enginetrends_data$cgi_show_alerts,
        smooth_window = enginetrends_data$smooth_window,
        rb_graph_size = enginetrends_data$rb_graph_size,
        rb_engine_position = enginetrends_data$rb_engine_position,
        color_engine = enginetrends_data$color_engine,
        ci_baseline = enginetrends_data$ci_baseline
      )
    }
    
  })
  
  output$enginetrends_reporttable <- DT::renderDataTable(server = FALSE,{
    
      req(enginetrends_data$params)

      if (is.null(enginetrends_data$params)){
        return()
      }
      else{
        browser()
        
        df <- enginetrends_data$params[,c(
          # "operator",
          "ac_reg_new",
          "aircraft_id",
          "aircraft_type",
          "engine_position",
          "engine_id",
          #"engine_type",
          "flight_phase",
          "flight_datetime",
          "parameter_name",
          "float_value"
        )]
        
        df <- df[!duplicated(df[,c(
          # "operator",
          "ac_reg_new",
          "aircraft_id",
          "aircraft_type",
          "engine_position",
          "engine_id",
          #"engine_type",
          "flight_phase",
          "flight_datetime",
          "parameter_name")]),]
        
        df_aircraft <- enginetrends_data$params_aircraft[,c(
          # "operator",
          "ac_reg_new",
          "aircraft_id",
          "aircraft_type",
          #"engine_type",
          "flight_phase",
          "flight_datetime",
          "parameter_name",
          "float_value"
        )]
        
        df_aircraft <- df_aircraft[!duplicated(df_aircraft[,c(
          # "operator",
          "ac_reg_new",
          "aircraft_id",
          "aircraft_type",
          #"engine_type",
          "flight_phase",
          "flight_datetime",
          "parameter_name"
        )]),]

        # df$float_value <- round(df$float_value,2)
        
        df <- df[!(df$parameter_name %in% unique(df_aircraft$parameter_name)),]
        
        # df_aircraft$float_value <- round(df_aircraft$float_value,2)
        
        df <- df %>%
          group_by(
            # operator,
            ac_reg_new,
            aircraft_id,
            aircraft_type,
            engine_position,
            engine_id,
            #engine_type,
            flight_phase,
            flight_datetime,
            parameter_name
          ) %>%
          mutate(row = row_number()) %>%
          tidyr::pivot_wider(
            names_from = parameter_name,
            values_from = float_value
          ) %>%
          select(-row)
        
        # df <- df[,c(
        #   # "operator",
        #   "ac_reg_new",
        #   "aircraft_id",
        #   "aircraft_type",
        #   "engine_position",
        #   "engine_id",
        #   #"engine_type",
        #   "flight_phase",
        #   "flight_datetime",
        #   "parameter_name",
        #   "float_value"
        # )] %>%
        #   distinct() %>%
        #   tidyr::pivot_wider(
        #     names_from = parameter_name,
        #     values_from = float_value
        #   ) 
        
        df_aircraft <- df_aircraft %>%
          group_by(
            # operator,
            ac_reg_new,
            aircraft_id,
            aircraft_type,
            #engine_type,
            flight_phase,
            flight_datetime,
            parameter_name
          ) %>%
          mutate(row = row_number()) %>%
          tidyr::pivot_wider(
            names_from = parameter_name,
            values_from = float_value
          ) %>%
          select(-row)
        
        # df_aircraft <- df_aircraft[,c(
        #   # "operator",
        #   "ac_reg_new",
        #   "aircraft_id",
        #   "aircraft_type",
        #   #"engine_type",
        #   "flight_phase",
        #   "flight_datetime",
        #   "parameter_name",
        #   "float_value"
        # )] %>%
        #   distinct() %>%
        #   tidyr::pivot_wider(
        #     names_from = parameter_name,
        #     values_from = float_value
        #   )
        
        df_aircraft <- df_aircraft[!duplicated(df_aircraft),]
        
        df$flight_datetime <- as.character(df$flight_datetime)
        
        df_aircraft$flight_datetime <- as.character(df_aircraft$flight_datetime)
        
        df <- df %>%
          left_join(
            df_aircraft,
            by = c(
              "ac_reg_new" = "ac_reg_new",
              "aircraft_id" = "aircraft_id",
              "aircraft_type" = "aircraft_type",
              #"engine_type",
              "flight_phase" = "flight_phase",
              "flight_datetime" = "flight_datetime"
            )
          )
        
        if(nrow(df) == 0){
          
          df <- df_aircraft
          
        }
        
        DT::datatable({
          df
        },
        caption = "Report table",
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
  
  
  output$enginetrends_maintenance <- DT::renderDataTable(server = FALSE,{
    
    req(enginetrends_data$maintenance)
    
    if (is.null(enginetrends_data$maintenance)){
      return()
    }
    else{
      DT::datatable({
        enginetrends_data$maintenance
      },
      caption = "Maintenance table",
      extensions = 'Buttons',
      
      options = list(
        dom = 'Bfrtip',
        
        buttons = list(
          list(
            extend = 'collection',  #'csv',
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
  
  observeEvent(input$create_maintenance,{
    
    showModal(
      modal_create_maintenance
    )
    
  })
  
  modal_create_maintenance <- modalDialog(
    fluidPage(
      h3(
        paste0(
          "Please enter maintenance action credits"
        )
      ),
      uiOutput(ns("ui_maintenance_engine_id")),
      dateInput(
        ns("di_maint_datetime"), 
        "Maintenance Date",
        value = as.Date(Sys.Date())
      ),
      uiOutput(ns("ui_maintenance_atacode")),
      textAreaInput(
        ns("ti_maintenance_reason"),
        "Reason"
      ),
      actionBttn(
        ns("ab_save_maintenance"), 
        "Save maintenance action", 
        color = "success"
      )
    ),
    size="l"
  )
  
  output$ui_maintenance_engine_id <- renderUI({
    
    pickerInput(
      ns("pi_maintenance_engine_id"),
      label = "Engine id",
      choices = unique(enginetrends_data$fleetsummary$engine_id), 
      options = list(
        `live-search`=TRUE
      ),
      multiple = F
    )
    
  })
  
  output$ui_maintenance_atacode <- renderUI({
      
    atacodecolor <- pool %>% 
      tbl(in_schema("ecmapp", "atacodecolor_operator")) %>% 
      filter(
        operator %in% !!input$enginetrends_operator_pi
      ) %>%
      collect()
    
    pickerInput(
      ns("pi_maintenance_atacode"),
      label = "Ata code",
      choices = atacodecolor$ata_code,
      choicesOpt = list(
        subtext = atacodecolor$description
      ), 
      options = list(
        `live-search`=TRUE
      ),
      multiple = F
    ) 
    
  })
  
  observeEvent(input$ab_save_maintenance,{
    # browser()
    new_maintenance <- data.frame(
      engine_id = input$pi_maintenance_engine_id,
      maint_datetime = input$di_maint_datetime,
      ata_code = input$pi_maintenance_atacode,
      ata_classification = NA,
      family = NA,
      reason = input$ti_maintenance_reason,
      author = credentials()$user,
      creation_datetime = Sys.time()
      #operator = input$enginetrends_operator_pi
    )
    
    enginetrends_data$maintenance <- rbind(
      enginetrends_data$maintenance[,colnames(new_maintenance)],
      new_maintenance
    )
    
    dbWriteTable(pool, c("ecmapp", "maintenance"), value = new_maintenance, row.names = FALSE, append = TRUE)
    
    removeModal()
    
    showNotification(
      paste0(
        "Maintenance has been created"
      )
    )
    
  })
  
  output$enginetrends_alerts <- DT::renderDataTable(server = FALSE,{
    
    req(enginetrends_data$alerts)
    
    if (is.null(enginetrends_data$maintenance)){
      return()
    }
    else{
      DT::datatable({
        enginetrends_data$alerts
      },
      caption = "Alerts table",
      extensions = 'Buttons',
      
      options = list(
        dom = 'Bfrtip',
        
        buttons = list(
          list(
            extend = 'collection',  #'csv',
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
  
  observeEvent(input$ab_export_enginetrends_preset, {
    screenshot(
      id = "enginetrends_preset_with_name",
      filename = "report_plot"
      # scale = 3
    )
  })
  
  output$enginetrends_preset_name <- renderUI({
    
    req(input$update_enginetrends_data)
    
    # browser()
    
    h4(
      paste0(
        "    ",
        input$enginetrends_presetname_pi,
        ": ",
        paste(
          input$enginetrends_acreg_pi,
          collapse = ","
        ),
        # " (",
        # aircraft_reg_old,
        # ")",
        " - ",
        paste(
          unique(enginetrends_data$fleetsummary$aircraft_type),#input$enginetrends_actype_pi,
          collapse = ","
        ),
        # input$enginetrends_actype_pi,
        " - ",
        input$enginetrends_operator_pi
      )  
    )
    
  })
  
  output$enginetrends_preset_with_name <- renderUI({
    
    fluidRow(
      # column(
      #   1
      # ),
      column(
        12,
        uiOutput(ns("enginetrends_preset_name")),
        br(),
        withSpinner(htmlOutput(ns("enginetrends_preset")))
      )
    )
    
  })
  
  output$enginetrends_workspace <- renderUI({
    
    #if(id_tab() == "engine_trends"){
      
      fluidRow(
        bs4Card(
          width = 12,
          headerBorder = FALSE,
          collapsible = FALSE,
          fluidRow(
            column(
              8,
              fluidRow(
                column(
                  3,
                  uiOutput(ns("enginetrends_operator"))
                ),
                column(
                  3,
                  uiOutput(ns("enginetrends_actype"))
                ),
                column(
                  3,
                  uiOutput(ns("enginetrends_acreg"))
                ),
                column(
                  3,
                  uiOutput(ns("enginetrends_presetname"))
                )
              )

            ),
            br(),
            column(1),
            column(
              3,
              hr(),
              fluidRow(
                uiOutput(ns("enginetrends_plotoptions")),
                actionBttn(ns("update_enginetrends_data"), "Update plots"),
                actionBttn(
                  ns("ab_prev"), 
                  "Prev",
                  size = "sm"
                  #,icon = icon("fa-backward-step")
                ),
                actionBttn(
                  ns("ab_next"),
                  "Next",
                  size = "sm"
                  #,icon = icon("fa-forward-step")
                )
              )
            )
          )
        ),
        
        bs4TabCard(
          width = 12,
          maximizable = TRUE,
          solidHeader = FALSE,
          sidebar = boxSidebar(),
          
          tabPanel(
            title = "Report plot",
            actionBttn(ns("ab_export_enginetrends_preset"), "Download image"),
            br(),
            div(
              style = 'overflow-y:scroll;height:1050px;',
              uiOutput(ns("enginetrends_preset_with_name"))
            )
            #uiOutput(ns("enginetrends_preset_with_name"))
            #withSpinner(uiOutput(ns("enginetrends_preset")))
          ),
          tabPanel(
            title = "Report table",
            withSpinner(DT::dataTableOutput(ns("enginetrends_reporttable")))
            # withSpinner(reactableOutput(ns("enginetrends_reporttable")))    
          ),
          tabPanel(
            title = "Maintenance table",
            withSpinner(DT::dataTableOutput(ns("enginetrends_maintenance"))),
            # withSpinner(reactableOutput(ns("enginetrends_maintenance"))),
            actionBttn(
              ns("create_maintenance"),
              "Create maintenance",
              color = "success"
            )
          ),
          tabPanel(
            title = "Alerts table",
            withSpinner(DT::dataTableOutput(ns("enginetrends_alerts")))
            # withSpinner(reactableOutput(ns("enginetrends_alerts"))) 
          )
        )  
      )
      
    #}
    
  })
  
  return(reactive({enginetrends_data}))
  
}